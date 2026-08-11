package projectreport

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

var stableID = regexp.MustCompile(`^[a-z0-9]+(?:-[a-z0-9]+)*$`)

func Load(profilePath, repoRoot string) (Report, error) {
	data, err := os.ReadFile(profilePath)
	if err != nil {
		return Report{}, fmt.Errorf("read profile: %w", err)
	}
	var profile Profile
	dec := json.NewDecoder(strings.NewReader(string(data)))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&profile); err != nil {
		return Report{}, fmt.Errorf("decode profile: %w", err)
	}
	root, err := filepath.Abs(repoRoot)
	if err != nil {
		return Report{}, fmt.Errorf("resolve repository: %w", err)
	}
	if err := validateAndEnrich(&profile, root); err != nil {
		return Report{}, err
	}
	commit, dirty := gitIdentity(root)
	profileSum := sha256.Sum256(data)
	return Report{
		Profile: profile, ProfileSHA256: hex.EncodeToString(profileSum[:]), RepoRoot: root,
		Commit: commit, Dirty: dirty, GeneratedAt: time.Now().UTC(),
	}, nil
}

func validateAndEnrich(profile *Profile, root string) error {
	if !stableID.MatchString(profile.ID) || strings.TrimSpace(profile.Name) == "" || strings.TrimSpace(profile.Tagline) == "" {
		return errors.New("profile requires a stable id, name, and tagline")
	}
	if len(profile.Features) == 0 {
		return errors.New("profile must contain at least one product capability")
	}
	seen := map[string]bool{}
	for fi := range profile.Features {
		feature := &profile.Features[fi]
		if !stableID.MatchString(feature.ID) || strings.TrimSpace(feature.Name) == "" || strings.TrimSpace(feature.Provides) == "" {
			return fmt.Errorf("feature %d requires a stable id, name, and human description", fi+1)
		}
		if seen[feature.ID] {
			return fmt.Errorf("duplicate feature id %q", feature.ID)
		}
		seen[feature.ID] = true
		if len(feature.Sources) == 0 {
			return fmt.Errorf("feature %q has no source evidence", feature.ID)
		}
		for si := range feature.Sources {
			if err := enrichSource(&feature.Sources[si], root); err != nil {
				return fmt.Errorf("feature %q: %w", feature.ID, err)
			}
		}
	}
	return nil
}

func enrichSource(source *Source, root string) error {
	clean := filepath.Clean(source.Path)
	if clean == "." || filepath.IsAbs(clean) || clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return fmt.Errorf("unsafe source path %q", source.Path)
	}
	path := filepath.Join(root, clean)
	rel, err := filepath.Rel(root, path)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return fmt.Errorf("source escapes repository: %q", source.Path)
	}
	file, err := openRepositoryFile(root, clean)
	if err != nil {
		return fmt.Errorf("open source %q: %w", source.Path, err)
	}
	defer file.Close()
	if source.LineStart < 1 || source.LineEnd < source.LineStart {
		return fmt.Errorf("invalid line range for %q", source.Path)
	}
	var selected []string
	line := 0
	scanner := bufio.NewScanner(file)
	buffer := make([]byte, 64*1024)
	scanner.Buffer(buffer, 1024*1024)
	for scanner.Scan() {
		line++
		if line >= source.LineStart && line <= source.LineEnd {
			selected = append(selected, scanner.Text())
		}
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("scan source %q: %w", source.Path, err)
	}
	if source.LineEnd > line {
		return fmt.Errorf("line range %d-%d exceeds %q (%d lines)", source.LineStart, source.LineEnd, source.Path, line)
	}
	sum := sha256.Sum256([]byte(strings.Join(selected, "\n")))
	source.SHA256 = hex.EncodeToString(sum[:])
	u := url.URL{Scheme: "file", Path: path, Fragment: fmt.Sprintf("L%d-L%d", source.LineStart, source.LineEnd)}
	source.URI = u.String()
	return nil
}

// openRepositoryFile refuses symlinks below the selected repository root and
// verifies that the opened descriptor still names the regular file inspected
// during traversal. Resolving the root itself keeps legitimate macOS paths
// such as /var -> /private/var usable without allowing an in-repository escape.
func openRepositoryFile(root, relative string) (*os.File, error) {
	resolvedRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return nil, fmt.Errorf("resolve repository root: %w", err)
	}
	current := resolvedRoot
	parts := strings.Split(filepath.Clean(relative), string(filepath.Separator))
	var inspected os.FileInfo
	for i, part := range parts {
		current = filepath.Join(current, part)
		info, err := os.Lstat(current)
		if err != nil {
			return nil, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, fmt.Errorf("symbolic link is not allowed inside repository: %s", relative)
		}
		if i < len(parts)-1 && !info.IsDir() {
			return nil, fmt.Errorf("source parent is not a directory: %s", relative)
		}
		inspected = info
	}
	if inspected == nil || !inspected.Mode().IsRegular() {
		return nil, fmt.Errorf("source is not a regular file: %s", relative)
	}
	file, err := os.Open(current)
	if err != nil {
		return nil, err
	}
	opened, err := file.Stat()
	if err != nil {
		_ = file.Close()
		return nil, err
	}
	if !opened.Mode().IsRegular() || !os.SameFile(inspected, opened) {
		_ = file.Close()
		return nil, fmt.Errorf("source identity changed while opening: %s", relative)
	}
	return file, nil
}

func gitIdentity(root string) (string, bool) {
	command := func(args ...string) string {
		cmd := exec.Command("git", append([]string{"-C", root}, args...)...)
		out, err := cmd.Output()
		if err != nil {
			return ""
		}
		return strings.TrimSpace(string(out))
	}
	commit := command("rev-parse", "HEAD")
	dirty := command("status", "--porcelain=v1") != ""
	return commit, dirty
}
