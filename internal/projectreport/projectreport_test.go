package projectreport

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWakuProfileRendersHumanCapabilityFirstReport(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", ".."))
	report, err := Load(
		filepath.Join(root, "profiles", "waku-agent.json"),
		filepath.Join(root, "..", "..", "repo", "waku-agent"),
	)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(report.Profile.Features); got != 9 {
		t.Fatalf("features=%d, want 9", got)
	}
	var output bytes.Buffer
	if err := Render(&output, report); err != nil {
		t.Fatal(err)
	}
	html := output.String()
	for _, want := range []string{
		"这个项目解决什么问题？",
		"它有哪些主要功能？",
		"每个功能是怎么做的？",
		"看完整体，应该怎么理解它？",
		"读完后，记住这几件事",
		"谁触发",
		"谁接管",
		"可直接借鉴",
		"不要照搬",
		"仍需验证",
		`id="feature-agent-loop"`,
		`id="feature-memory"`,
		`id="feature-voice"`,
		"功能语义来自已审阅的项目 profile",
		"不是全自动语义抽取结果",
		"关键源码证据 · 建议按顺序阅读",
		"阅读 1",
	} {
		if !strings.Contains(html, want) {
			t.Errorf("report missing %q", want)
		}
	}
	if strings.Contains(html, "主参考") || strings.Contains(html, "自动排名") {
		t.Fatal("project report must explain one project, not choose between projects")
	}
	if strings.Contains(html, "#ZgotmplZ") {
		t.Fatal("validated local source links were rejected by html/template")
	}
}

func TestVerifyBundleRejectsResignedModuleCoverageMismatch(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", ".."))
	profile := filepath.Join(root, "profiles", "waku-agent.json")
	repo := filepath.Join(root, "..", "..", "repo", "waku-agent")
	report, err := Load(profile, repo)
	if err != nil {
		t.Fatal(err)
	}
	bundle := filepath.Join(t.TempDir(), "waku-agent")
	if err := WriteBundle(bundle, report); err != nil {
		t.Fatal(err)
	}
	var modules ModulesArtifact
	if err := decodeJSON(filepath.Join(bundle, "modules.json"), &modules); err != nil {
		t.Fatal(err)
	}
	modules.Features[0].ReadingOrder = append(modules.Features[0].ReadingOrder, modules.Features[0].ReadingOrder[0])
	content, err := prettyJSON(modules)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "modules.json"), content, 0o644); err != nil {
		t.Fatal(err)
	}
	resignManifest(t, bundle, "modules.json", content)
	if err := VerifyBundle(bundle, repo, profile); err == nil || !strings.Contains(err.Error(), "report/modules mismatch") {
		t.Fatalf("VerifyBundle error=%v, want report/modules mismatch", err)
	}
}

func TestVerifyBundleRejectsResignedManifestOmission(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", ".."))
	profile := filepath.Join(root, "profiles", "waku-agent.json")
	repo := filepath.Join(root, "..", "..", "repo", "waku-agent")
	report, err := Load(profile, repo)
	if err != nil {
		t.Fatal(err)
	}
	bundle := filepath.Join(t.TempDir(), "waku-agent")
	if err := WriteBundle(bundle, report); err != nil {
		t.Fatal(err)
	}
	var manifest Manifest
	if err := decodeJSON(filepath.Join(bundle, "manifest.json"), &manifest); err != nil {
		t.Fatal(err)
	}
	manifest.Files = manifest.Files[:len(manifest.Files)-1]
	manifest.GenerationID = generationID(manifest.Files)
	content, err := prettyJSON(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "manifest.json"), content, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := VerifyBundle(bundle, repo, profile); err == nil || !strings.Contains(err.Error(), "exact report artifact set") {
		t.Fatalf("VerifyBundle error=%v, want exact artifact-set rejection", err)
	}
}

func TestVerifyBundleRejectsResignedNarrativeDifferentFromReviewedProfile(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", ".."))
	profile := filepath.Join(root, "profiles", "waku-agent.json")
	repo := filepath.Join(root, "..", "..", "repo", "waku-agent")
	report, err := Load(profile, repo)
	if err != nil {
		t.Fatal(err)
	}
	bundle := filepath.Join(t.TempDir(), "waku-agent")
	if err := WriteBundle(bundle, report); err != nil {
		t.Fatal(err)
	}
	var artifact ReportArtifact
	if err := decodeJSON(filepath.Join(bundle, "report.json"), &artifact); err != nil {
		t.Fatal(err)
	}
	artifact.Profile.Tagline = "A different, re-signed narrative"
	content, err := prettyJSON(artifact)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "report.json"), content, 0o644); err != nil {
		t.Fatal(err)
	}
	resignManifest(t, bundle, "report.json", content)
	if err := VerifyBundle(bundle, repo, profile); err == nil || !strings.Contains(err.Error(), "reviewed profile") {
		t.Fatalf("VerifyBundle error=%v, want reviewed-profile rejection", err)
	}
}

func TestVerifyBundleRejectsResignedHTMLDifferentFromVerifiedReport(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", ".."))
	profile := filepath.Join(root, "profiles", "waku-agent.json")
	repo := filepath.Join(root, "..", "..", "repo", "waku-agent")
	report, err := Load(profile, repo)
	if err != nil {
		t.Fatal(err)
	}
	bundle := filepath.Join(t.TempDir(), "waku-agent")
	if err := WriteBundle(bundle, report); err != nil {
		t.Fatal(err)
	}
	content := []byte("<!doctype html><title>re-signed but not canonical</title>\n")
	if err := os.WriteFile(filepath.Join(bundle, "index.html"), content, 0o644); err != nil {
		t.Fatal(err)
	}
	resignManifest(t, bundle, "index.html", content)
	if err := VerifyBundle(bundle, repo, profile); err == nil || !strings.Contains(err.Error(), "verified human report") {
		t.Fatalf("VerifyBundle error=%v, want canonical HTML rejection", err)
	}
}

func TestWriteAndVerifyWakuReportBundle(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", ".."))
	repo := filepath.Join(root, "..", "..", "repo", "waku-agent")
	report, err := Load(filepath.Join(root, "profiles", "waku-agent.json"), repo)
	if err != nil {
		t.Fatal(err)
	}
	bundle := filepath.Join(t.TempDir(), "waku-agent")
	if err := WriteBundle(bundle, report); err != nil {
		t.Fatal(err)
	}
	for _, name := range bundleFiles {
		info, err := os.Stat(filepath.Join(bundle, name))
		if err != nil || !info.Mode().IsRegular() {
			t.Fatalf("bundle file %s: %v", name, err)
		}
	}
	profile := filepath.Join(root, "profiles", "waku-agent.json")
	if err := VerifyBundle(bundle, repo, profile); err != nil {
		t.Fatal(err)
	}
	var evidence EvidenceArtifact
	data, err := os.ReadFile(filepath.Join(bundle, "evidence.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(data, &evidence); err != nil {
		t.Fatal(err)
	}
	if len(evidence.Items) < 9 {
		t.Fatalf("evidence items=%d, want at least one per Waku capability", len(evidence.Items))
	}
}

func TestVerifyBundleRejectsArtifactTampering(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", ".."))
	repo := filepath.Join(root, "..", "..", "repo", "waku-agent")
	report, err := Load(filepath.Join(root, "profiles", "waku-agent.json"), repo)
	if err != nil {
		t.Fatal(err)
	}
	bundle := filepath.Join(t.TempDir(), "waku-agent")
	if err := WriteBundle(bundle, report); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "report.json"), []byte("{}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	profile := filepath.Join(root, "profiles", "waku-agent.json")
	if err := VerifyBundle(bundle, repo, profile); err == nil || !strings.Contains(err.Error(), "integrity mismatch") {
		t.Fatalf("VerifyBundle error=%v, want integrity mismatch", err)
	}
}

func TestWriteBundleRefusesExistingDestination(t *testing.T) {
	report := Report{Profile: Profile{ID: "safe", Name: "Safe", Tagline: "Safe"}}
	output := filepath.Join(t.TempDir(), "existing")
	if err := os.Mkdir(output, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := WriteBundle(output, report); err == nil || !strings.Contains(err.Error(), "already exists") {
		t.Fatalf("WriteBundle error=%v, want existing output rejection", err)
	}
}

func TestLoadFailsClosedForEscapingOrMissingEvidence(t *testing.T) {
	repo := t.TempDir()
	profile := filepath.Join(t.TempDir(), "bad.json")
	data := `{"id":"bad","name":"Bad","tagline":"Bad","features":[{"id":"one","name":"One","provides":"One","sources":[{"path":"../outside","line_start":1,"line_end":1}]}]}`
	if err := os.WriteFile(profile, []byte(data), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(profile, repo); err == nil || !strings.Contains(err.Error(), "unsafe source path") {
		t.Fatalf("Load error=%v, want unsafe source path", err)
	}
}

func TestLoadRejectsRepositorySymlinkToExternalEvidence(t *testing.T) {
	repo := t.TempDir()
	external := filepath.Join(t.TempDir(), "secret.py")
	if err := os.WriteFile(external, []byte("SECRET = True\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(external, filepath.Join(repo, "evidence.py")); err != nil {
		t.Fatal(err)
	}
	profile := filepath.Join(t.TempDir(), "profile.json")
	data := `{"id":"safe","name":"Safe","tagline":"Safe","features":[{"id":"one","name":"One","provides":"One","sources":[{"path":"evidence.py","line_start":1,"line_end":1}]}]}`
	if err := os.WriteFile(profile, []byte(data), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(profile, repo); err == nil || !strings.Contains(err.Error(), "symbolic link") {
		t.Fatalf("Load error=%v, want symbolic link rejection", err)
	}
}

func TestVerifyBundleRejectsResignedReportEvidenceMismatch(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", ".."))
	repo := filepath.Join(root, "..", "..", "repo", "waku-agent")
	report, err := Load(filepath.Join(root, "profiles", "waku-agent.json"), repo)
	if err != nil {
		t.Fatal(err)
	}
	bundle := filepath.Join(t.TempDir(), "waku-agent")
	if err := WriteBundle(bundle, report); err != nil {
		t.Fatal(err)
	}
	var artifact ReportArtifact
	if err := decodeJSON(filepath.Join(bundle, "report.json"), &artifact); err != nil {
		t.Fatal(err)
	}
	artifact.Profile.Features[0].Sources = artifact.Profile.Features[0].Sources[1:]
	content, err := prettyJSON(artifact)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "report.json"), content, 0o644); err != nil {
		t.Fatal(err)
	}
	resignManifest(t, bundle, "report.json", content)
	profile := filepath.Join(root, "profiles", "waku-agent.json")
	if err := VerifyBundle(bundle, repo, profile); err == nil || !strings.Contains(err.Error(), "report/evidence mismatch") {
		t.Fatalf("VerifyBundle error=%v, want report/evidence mismatch", err)
	}
}

func resignManifest(t *testing.T, bundle, changed string, content []byte) {
	t.Helper()
	var manifest Manifest
	if err := decodeJSON(filepath.Join(bundle, "manifest.json"), &manifest); err != nil {
		t.Fatal(err)
	}
	for i := range manifest.Files {
		if manifest.Files[i].Path == changed {
			manifest.Files[i] = manifestEntry(changed, content)
		}
	}
	manifest.GenerationID = generationID(manifest.Files)
	data, err := prettyJSON(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bundle, "manifest.json"), data, 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestTemplateEscapesUntrustedProfileText(t *testing.T) {
	report := Report{Profile: Profile{
		ID: "safe", Name: `<script>alert(1)</script>`, Tagline: "safe", Highlights: []string{"ok"},
		Features: []Feature{{
			ID: "feature", Name: "Feature", Provides: "Useful", Sources: []Source{{Path: "main.py", LineStart: 1, LineEnd: 1, URI: "file:///tmp/main.py#L1"}},
		}},
	}}
	var output bytes.Buffer
	if err := Render(&output, report); err != nil {
		t.Fatal(err)
	}
	if strings.Contains(output.String(), `<script>alert(1)</script>`) {
		t.Fatal("profile text was not escaped")
	}
}
