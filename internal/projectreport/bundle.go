package projectreport

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"time"
)

const BundleSchemaVersion = "1.0"

var bundleFiles = []string{"evidence.json", "index.html", "manifest.json", "modules.json", "report.json"}

type ProjectSnapshot struct {
	Root   string `json:"root"`
	Remote string `json:"remote"`
	Commit string `json:"commit"`
	Dirty  bool   `json:"dirty"`
}

type ReportArtifact struct {
	SchemaVersion   string          `json:"schema_version"`
	GeneratedAt     string          `json:"generated_at"`
	NarrativeSource string          `json:"narrative_source"`
	ProfileSHA256   string          `json:"profile_sha256"`
	Project         ProjectSnapshot `json:"project"`
	Profile         Profile         `json:"profile"`
}

type EvidenceArtifact struct {
	SchemaVersion string         `json:"schema_version"`
	ProjectID     string         `json:"project_id"`
	Items         []EvidenceItem `json:"items"`
}

type EvidenceItem struct {
	ID        string `json:"id"`
	FeatureID string `json:"feature_id"`
	Path      string `json:"path"`
	Symbol    string `json:"symbol,omitempty"`
	LineStart int    `json:"line_start"`
	LineEnd   int    `json:"line_end"`
	Reason    string `json:"reason"`
	SHA256    string `json:"sha256"`
	URI       string `json:"uri"`
}

type ModulesArtifact struct {
	SchemaVersion string          `json:"schema_version"`
	ProjectID     string          `json:"project_id"`
	Features      []FeatureModule `json:"features"`
}

type FeatureModule struct {
	FeatureID    string       `json:"feature_id"`
	FeatureName  string       `json:"feature_name"`
	Modules      []ModuleItem `json:"modules"`
	ReadingOrder []string     `json:"reading_order"`
}

type ModuleItem struct {
	Path       string   `json:"path"`
	SourceRefs []string `json:"source_refs"`
}

type Manifest struct {
	SchemaVersion string          `json:"schema_version"`
	GenerationID  string          `json:"generation_id"`
	Files         []ManifestEntry `json:"files"`
}

type ManifestEntry struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
	Bytes  int    `json:"bytes"`
}

// WriteBundle publishes one immutable report directory. Refusing an existing
// destination prevents a failed update from mixing generations.
func WriteBundle(outputDir string, report Report) error {
	outputDir, err := filepath.Abs(outputDir)
	if err != nil {
		return fmt.Errorf("resolve output directory: %w", err)
	}
	if _, err := os.Lstat(outputDir); err == nil {
		return fmt.Errorf("output already exists: %s", outputDir)
	} else if !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("inspect output: %w", err)
	}
	parent := filepath.Dir(outputDir)
	if err := os.MkdirAll(parent, 0o755); err != nil {
		return fmt.Errorf("create output parent: %w", err)
	}
	stage, err := os.MkdirTemp(parent, ".repo-teacher-stage-")
	if err != nil {
		return fmt.Errorf("create staging directory: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = os.RemoveAll(stage)
		}
	}()

	reportJSON, evidenceJSON, modulesJSON, err := artifactJSON(report)
	if err != nil {
		return err
	}
	var html bytes.Buffer
	if err := Render(&html, report); err != nil {
		return err
	}
	artifacts := map[string][]byte{
		"index.html":    html.Bytes(),
		"report.json":   reportJSON,
		"evidence.json": evidenceJSON,
		"modules.json":  modulesJSON,
	}
	entries := make([]ManifestEntry, 0, len(artifacts))
	for _, name := range []string{"evidence.json", "index.html", "modules.json", "report.json"} {
		content := artifacts[name]
		if err := writeSynced(filepath.Join(stage, name), content); err != nil {
			return err
		}
		entries = append(entries, manifestEntry(name, content))
	}
	generationID := generationID(entries)
	manifestJSON, err := prettyJSON(Manifest{SchemaVersion: BundleSchemaVersion, GenerationID: generationID, Files: entries})
	if err != nil {
		return fmt.Errorf("encode manifest: %w", err)
	}
	if err := writeSynced(filepath.Join(stage, "manifest.json"), manifestJSON); err != nil {
		return err
	}
	if err := syncDirectory(stage); err != nil {
		return err
	}
	if err := os.Rename(stage, outputDir); err != nil {
		return fmt.Errorf("publish bundle: %w", err)
	}
	if err := syncDirectory(parent); err != nil {
		return err
	}
	committed = true
	return nil
}

func artifactJSON(report Report) ([]byte, []byte, []byte, error) {
	reportArtifact := ReportArtifact{
		SchemaVersion:   BundleSchemaVersion,
		GeneratedAt:     report.GeneratedAt.Format(time.RFC3339Nano),
		NarrativeSource: "reviewed-profile",
		ProfileSHA256:   report.ProfileSHA256,
		Project: ProjectSnapshot{
			Root: report.RepoRoot, Remote: report.Profile.Remote, Commit: report.Commit, Dirty: report.Dirty,
		},
		Profile: report.Profile,
	}
	evidence, modules := artifactsForProfile(report.Profile)
	reportJSON, err := prettyJSON(reportArtifact)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("encode report: %w", err)
	}
	evidenceJSON, err := prettyJSON(evidence)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("encode evidence: %w", err)
	}
	modulesJSON, err := prettyJSON(modules)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("encode modules: %w", err)
	}
	return reportJSON, evidenceJSON, modulesJSON, nil
}

func prettyJSON(value any) ([]byte, error) {
	var out bytes.Buffer
	encoder := json.NewEncoder(&out)
	encoder.SetEscapeHTML(true)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

func evidenceID(featureID string, source Source) string {
	value := fmt.Sprintf("%s\x00%s\x00%s\x00%d\x00%d", featureID, source.Path, source.Symbol, source.LineStart, source.LineEnd)
	sum := sha256.Sum256([]byte(value))
	return "evidence-" + hex.EncodeToString(sum[:8])
}

func modulePath(path string) string {
	dir := filepath.ToSlash(filepath.Dir(path))
	if dir == "." {
		return "repository-root"
	}
	parts := strings.Split(dir, "/")
	if len(parts) > 2 {
		return strings.Join(parts[:2], "/")
	}
	return dir
}

func manifestEntry(path string, content []byte) ManifestEntry {
	sum := sha256.Sum256(content)
	return ManifestEntry{Path: path, SHA256: hex.EncodeToString(sum[:]), Bytes: len(content)}
}

func generationID(entries []ManifestEntry) string {
	h := sha256.New()
	for _, entry := range entries {
		_, _ = io.WriteString(h, entry.Path+"\x00"+entry.SHA256+"\n")
	}
	return hex.EncodeToString(h.Sum(nil))
}

func writeSynced(path string, content []byte) error {
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
	if err != nil {
		return fmt.Errorf("create %s: %w", filepath.Base(path), err)
	}
	if _, err := file.Write(content); err != nil {
		_ = file.Close()
		return fmt.Errorf("write %s: %w", filepath.Base(path), err)
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		return fmt.Errorf("sync %s: %w", filepath.Base(path), err)
	}
	if err := file.Close(); err != nil {
		return fmt.Errorf("close %s: %w", filepath.Base(path), err)
	}
	return nil
}

func syncDirectory(path string) error {
	dir, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("open directory for sync: %w", err)
	}
	defer dir.Close()
	if err := dir.Sync(); err != nil {
		return fmt.Errorf("sync directory: %w", err)
	}
	return nil
}

func decodeJSON(path string, value any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	return decoder.Decode(value)
}

// VerifyBundle proves both artifact integrity and the source ranges backing
// every human-facing feature claim.
func VerifyBundle(bundleDir, repoRoot, profilePath string) error {
	bundleDir, err := filepath.Abs(bundleDir)
	if err != nil {
		return fmt.Errorf("resolve bundle: %w", err)
	}
	repoRoot, err = filepath.Abs(repoRoot)
	if err != nil {
		return fmt.Errorf("resolve repository: %w", err)
	}
	if err := verifyClosedSet(bundleDir); err != nil {
		return err
	}
	var manifest Manifest
	if err := decodeJSON(filepath.Join(bundleDir, "manifest.json"), &manifest); err != nil {
		return fmt.Errorf("decode manifest: %w", err)
	}
	if manifest.SchemaVersion != BundleSchemaVersion || manifest.GenerationID != generationID(manifest.Files) {
		return errors.New("manifest schema or generation id mismatch")
	}
	expectedManifestFiles := []string{"evidence.json", "index.html", "modules.json", "report.json"}
	if len(manifest.Files) != len(expectedManifestFiles) {
		return errors.New("manifest does not describe the exact report artifact set")
	}
	for _, entry := range manifest.Files {
		if filepath.Base(entry.Path) != entry.Path || entry.Path == "manifest.json" {
			return fmt.Errorf("unsafe manifest entry %q", entry.Path)
		}
		content, err := os.ReadFile(filepath.Join(bundleDir, entry.Path))
		if err != nil {
			return fmt.Errorf("read artifact %q: %w", entry.Path, err)
		}
		actual := manifestEntry(entry.Path, content)
		if actual.SHA256 != entry.SHA256 || actual.Bytes != entry.Bytes {
			return fmt.Errorf("artifact integrity mismatch: %s", entry.Path)
		}
	}
	for i, name := range expectedManifestFiles {
		if manifest.Files[i].Path != name {
			return errors.New("manifest does not describe the exact report artifact set")
		}
	}
	var report ReportArtifact
	if err := decodeJSON(filepath.Join(bundleDir, "report.json"), &report); err != nil {
		return fmt.Errorf("decode report: %w", err)
	}
	var evidence EvidenceArtifact
	if err := decodeJSON(filepath.Join(bundleDir, "evidence.json"), &evidence); err != nil {
		return fmt.Errorf("decode evidence: %w", err)
	}
	var modules ModulesArtifact
	if err := decodeJSON(filepath.Join(bundleDir, "modules.json"), &modules); err != nil {
		return fmt.Errorf("decode modules: %w", err)
	}
	if report.SchemaVersion != BundleSchemaVersion || evidence.SchemaVersion != BundleSchemaVersion || modules.SchemaVersion != BundleSchemaVersion {
		return errors.New("artifact schema mismatch")
	}
	if report.NarrativeSource != "reviewed-profile" {
		return errors.New("report does not declare its reviewed narrative source")
	}
	if report.Profile.ID != evidence.ProjectID || report.Profile.ID != modules.ProjectID {
		return errors.New("project identity mismatch across artifacts")
	}
	if report.Project.Remote != report.Profile.Remote {
		return errors.New("project remote differs from reviewed profile")
	}
	commit, dirty := gitIdentity(repoRoot)
	if report.Project.Root != repoRoot || report.Project.Commit != commit || report.Project.Dirty != dirty {
		return errors.New("repository snapshot changed since report generation")
	}
	verifiedProfile := report.Profile
	if err := validateAndEnrich(&verifiedProfile, repoRoot); err != nil {
		return fmt.Errorf("verify report profile: %w", err)
	}
	expectedEvidence, expectedModules := artifactsForProfile(verifiedProfile)
	if !reflect.DeepEqual(evidence, expectedEvidence) {
		return errors.New("report/evidence mismatch")
	}
	if !reflect.DeepEqual(modules, expectedModules) {
		return errors.New("report/modules mismatch")
	}
	expectedReport, err := Load(profilePath, repoRoot)
	if err != nil {
		return fmt.Errorf("load reviewed profile: %w", err)
	}
	if report.ProfileSHA256 != expectedReport.ProfileSHA256 || !sameJSONValue(report.Profile, expectedReport.Profile) {
		return errors.New("report differs from reviewed profile")
	}
	generatedAt, err := time.Parse(time.RFC3339Nano, report.GeneratedAt)
	if err != nil {
		return errors.New("report has an invalid generation timestamp")
	}
	canonicalReport := Report{
		Profile: verifiedProfile, ProfileSHA256: report.ProfileSHA256, RepoRoot: repoRoot,
		Commit: report.Project.Commit, Dirty: report.Project.Dirty, GeneratedAt: generatedAt,
	}
	var canonicalHTML bytes.Buffer
	if err := Render(&canonicalHTML, canonicalReport); err != nil {
		return err
	}
	actualHTML, err := os.ReadFile(filepath.Join(bundleDir, "index.html"))
	if err != nil {
		return fmt.Errorf("read index.html: %w", err)
	}
	if !bytes.Equal(actualHTML, canonicalHTML.Bytes()) {
		return errors.New("index.html differs from the verified human report")
	}
	featureIDs := map[string]bool{}
	for _, feature := range report.Profile.Features {
		featureIDs[feature.ID] = true
	}
	evidenceIDs := map[string]bool{}
	featureEvidence := map[string]int{}
	for _, item := range evidence.Items {
		if evidenceIDs[item.ID] || !featureIDs[item.FeatureID] {
			return fmt.Errorf("invalid evidence identity %q", item.ID)
		}
		evidenceIDs[item.ID] = true
		featureEvidence[item.FeatureID]++
		source := Source{Path: item.Path, Symbol: item.Symbol, LineStart: item.LineStart, LineEnd: item.LineEnd}
		if err := enrichSource(&source, repoRoot); err != nil {
			return fmt.Errorf("verify evidence %q: %w", item.ID, err)
		}
		if source.SHA256 != item.SHA256 || source.URI != item.URI || evidenceID(item.FeatureID, source) != item.ID {
			return fmt.Errorf("source evidence changed: %s", item.ID)
		}
	}
	for id := range featureIDs {
		if featureEvidence[id] == 0 {
			return fmt.Errorf("feature %q has no evidence", id)
		}
	}
	if err := verifyModules(modules, featureIDs, evidenceIDs); err != nil {
		return err
	}
	return nil
}

func artifactsForProfile(profile Profile) (EvidenceArtifact, ModulesArtifact) {
	evidence := EvidenceArtifact{SchemaVersion: BundleSchemaVersion, ProjectID: profile.ID}
	modules := ModulesArtifact{SchemaVersion: BundleSchemaVersion, ProjectID: profile.ID}
	for _, feature := range profile.Features {
		featureModules := FeatureModule{FeatureID: feature.ID, FeatureName: feature.Name}
		moduleRefs := map[string][]string{}
		for _, source := range feature.Sources {
			id := evidenceID(feature.ID, source)
			evidence.Items = append(evidence.Items, EvidenceItem{
				ID: id, FeatureID: feature.ID, Path: source.Path, Symbol: source.Symbol,
				LineStart: source.LineStart, LineEnd: source.LineEnd, Reason: source.Reason,
				SHA256: source.SHA256, URI: source.URI,
			})
			featureModules.ReadingOrder = append(featureModules.ReadingOrder, id)
			module := modulePath(source.Path)
			moduleRefs[module] = append(moduleRefs[module], id)
		}
		moduleNames := make([]string, 0, len(moduleRefs))
		for name := range moduleRefs {
			moduleNames = append(moduleNames, name)
		}
		sort.Strings(moduleNames)
		for _, name := range moduleNames {
			featureModules.Modules = append(featureModules.Modules, ModuleItem{Path: name, SourceRefs: moduleRefs[name]})
		}
		modules.Features = append(modules.Features, featureModules)
	}
	return evidence, modules
}

func sameJSONValue(left, right any) bool {
	leftJSON, leftErr := json.Marshal(left)
	rightJSON, rightErr := json.Marshal(right)
	return leftErr == nil && rightErr == nil && bytes.Equal(leftJSON, rightJSON)
}

func verifyClosedSet(bundleDir string) error {
	entries, err := os.ReadDir(bundleDir)
	if err != nil {
		return fmt.Errorf("read bundle: %w", err)
	}
	actual := make([]string, 0, len(entries))
	for _, entry := range entries {
		if entry.Type()&os.ModeSymlink != 0 || !entry.Type().IsRegular() {
			return fmt.Errorf("unexpected non-regular bundle entry: %s", entry.Name())
		}
		actual = append(actual, entry.Name())
	}
	sort.Strings(actual)
	if strings.Join(actual, "\x00") != strings.Join(bundleFiles, "\x00") {
		return fmt.Errorf("unexpected bundle contents: %v", actual)
	}
	return nil
}

func verifyModules(modules ModulesArtifact, featureIDs, evidenceIDs map[string]bool) error {
	seen := map[string]bool{}
	for _, feature := range modules.Features {
		if !featureIDs[feature.FeatureID] || seen[feature.FeatureID] {
			return fmt.Errorf("invalid module feature %q", feature.FeatureID)
		}
		seen[feature.FeatureID] = true
		for _, id := range feature.ReadingOrder {
			if !evidenceIDs[id] {
				return fmt.Errorf("module index references missing evidence %q", id)
			}
		}
		for _, module := range feature.Modules {
			if strings.TrimSpace(module.Path) == "" {
				return errors.New("module index contains an empty path")
			}
			for _, id := range module.SourceRefs {
				if !evidenceIDs[id] {
					return fmt.Errorf("module references missing evidence %q", id)
				}
			}
		}
	}
	if len(seen) != len(featureIDs) {
		return errors.New("module index does not cover every feature")
	}
	return nil
}
