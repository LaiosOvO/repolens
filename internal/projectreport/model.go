package projectreport

import "time"

// Profile is the human-facing contract for one repository. It deliberately
// starts with product capabilities; source locations are supporting evidence.
type Profile struct {
	ID                  string    `json:"id"`
	Name                string    `json:"name"`
	Tagline             string    `json:"tagline"`
	Description         string    `json:"description"`
	Audience            string    `json:"audience"`
	ProductForm         string    `json:"product_form"`
	License             string    `json:"license"`
	Remote              string    `json:"remote"`
	Highlights          []string  `json:"highlights"`
	ArchitectureSummary string    `json:"architecture_summary,omitempty"`
	Strengths           []string  `json:"strengths,omitempty"`
	Limitations         []string  `json:"limitations,omitempty"`
	ReferenceFit        string    `json:"reference_fit,omitempty"`
	ComparisonQuestions []string  `json:"comparison_questions,omitempty"`
	Conclusions         []string  `json:"conclusions,omitempty"`
	Features            []Feature `json:"features"`
}

type Feature struct {
	ID           string   `json:"id"`
	Name         string   `json:"name"`
	Provides     string   `json:"provides"`
	Trigger      string   `json:"trigger"`
	Owner        string   `json:"owner"`
	Output       string   `json:"output"`
	Consumer     string   `json:"consumer"`
	Mechanism    string   `json:"mechanism"`
	Technologies []string `json:"technologies"`
	Reuse        string   `json:"reuse"`
	Adapt        string   `json:"adapt"`
	Avoid        string   `json:"avoid"`
	Unknown      string   `json:"unknown"`
	Sources      []Source `json:"sources"`
}

type Source struct {
	Path      string `json:"path"`
	Symbol    string `json:"symbol"`
	LineStart int    `json:"line_start"`
	LineEnd   int    `json:"line_end"`
	Reason    string `json:"reason"`
	SHA256    string `json:"-"`
	URI       string `json:"-"`
}

type Report struct {
	Profile       Profile
	ProfileSHA256 string
	RepoRoot      string
	Commit        string
	Dirty         bool
	GeneratedAt   time.Time
}
