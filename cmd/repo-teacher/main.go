package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/local/repo-teacher/internal/projectreport"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	switch os.Args[1] {
	case "report":
		runReport(os.Args[2:])
	case "verify":
		runVerify(os.Args[2:])
	default:
		usage()
		os.Exit(2)
	}
}

func runReport(args []string) {
	flags := flag.NewFlagSet("report", flag.ExitOnError)
	repo := flags.String("repo", "", "local repository to explain")
	profile := flags.String("profile", "", "reviewed project profile")
	output := flags.String("output", "", "new report bundle directory")
	_ = flags.Parse(args)
	if *repo == "" || *profile == "" || *output == "" {
		flags.Usage()
		os.Exit(2)
	}
	report, err := projectreport.Load(*profile, *repo)
	if err != nil {
		fatal(err)
	}
	if err := projectreport.WriteBundle(*output, report); err != nil {
		fatal(err)
	}
	fmt.Println(*output)
}

func runVerify(args []string) {
	flags := flag.NewFlagSet("verify", flag.ExitOnError)
	repo := flags.String("repo", "", "source repository used to generate the report")
	profile := flags.String("profile", "", "reviewed project profile used to generate the report")
	bundle := flags.String("bundle", "", "report bundle directory")
	_ = flags.Parse(args)
	if *repo == "" || *profile == "" || *bundle == "" {
		flags.Usage()
		os.Exit(2)
	}
	if err := projectreport.VerifyBundle(*bundle, *repo, *profile); err != nil {
		fatal(err)
	}
	fmt.Println("verified", *bundle)
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage:")
	fmt.Fprintln(os.Stderr, "  repo-teacher report --repo <path> --profile <project.json> --output <new-report-dir>")
	fmt.Fprintln(os.Stderr, "  repo-teacher verify --repo <path> --profile <project.json> --bundle <report-dir>")
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "repo-teacher:", err)
	os.Exit(1)
}
