package main

import (
	"flag"
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	switch os.Args[1] {
	case "entrypoint":
		os.Exit(runEntrypoint(os.Args[2:]))
	default:
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: fullsend entrypoint STAGE [--scm NAME]")
}

func runEntrypoint(args []string) int {
	if len(args) < 1 {
		usage()
		return 2
	}
	stage := args[0]
	fs := flag.NewFlagSet("entrypoint", flag.ExitOnError)
	fs.Usage = func() {
		fmt.Fprintf(fs.Output(), "Usage: fullsend entrypoint STAGE [--scm NAME]\n")
		fs.PrintDefaults()
	}
	var scm string
	fs.StringVar(&scm, "scm", "github", "SCM backend")
	if err := fs.Parse(args[1:]); err != nil {
		return 2
	}
	if fs.NArg() != 0 {
		fs.Usage()
		return 2
	}
	_ = stage
	_ = scm
	return 0
}
