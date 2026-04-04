#!/usr/bin/env python3
"""
CLI runner for prompt-only skills.

Usage:
    python runner/run_skill.py --skill identify-call-roles --file examples/sample_transcript.txt
    python runner/run_skill.py --skill identify-call-roles --text "SPEAKER_A: Hello..."
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skill_runtime import load_skill, validate_skill, run_skill, discover_all_skills


def main():
    parser = argparse.ArgumentParser(
        description="Run a prompt-only skill with local LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --skill identify-call-roles --file examples/sample_transcript.txt
  %(prog)s --skill identify-call-roles --text "SPEAKER_A: Hello, how can I help?"
  %(prog)s --list
        """
    )
    
    parser.add_argument(
        '--skill',
        type=str,
        help='Name of the skill to run'
    )
    
    parser.add_argument(
        '--file',
        type=str,
        help='Path to input text file'
    )
    
    parser.add_argument(
        '--text',
        type=str,
        help='Input text directly'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available skills'
    )
    
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate the skill without running it'
    )
    
    parser.add_argument(
        '--no-validation',
        action='store_true',
        help='Skip validation before running'
    )
    
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # List skills mode
    if args.list:
        skills = discover_all_skills()
        if not skills:
            print("No skills found in skills/ directory")
            return 0
        
        print(f"Available skills ({len(skills)}):")
        for skill in skills:
            print(f"  - {skill}")
        return 0
    
    # Validate arguments
    if not args.skill:
        parser.error("--skill is required (or use --list to see available skills)")
    
    if not args.validate_only and not args.file and not args.text:
        parser.error("Either --file or --text is required")
    
    if args.file and args.text:
        parser.error("Cannot use both --file and --text")
    
    # Load skill
    if args.verbose:
        print(f"Loading skill: {args.skill}", file=sys.stderr)
    
    try:
        bundle = load_skill(args.skill)
    except Exception as e:
        print(f"Error loading skill '{args.skill}': {e}", file=sys.stderr)
        return 1
    
    if args.verbose:
        print(f"✓ Skill loaded: {bundle['name']}", file=sys.stderr)
    
    # Validate skill
    if not args.no_validation:
        if args.verbose:
            print("Validating skill...", file=sys.stderr)
        
        is_valid, errors = validate_skill(args.skill, bundle)
        
        if not is_valid:
            print(f"Skill validation failed:", file=sys.stderr)
            for error in errors:
                print(f"  ✗ {error}", file=sys.stderr)
            return 1
        
        if args.verbose:
            print("✓ Skill validation passed", file=sys.stderr)
    
    # Validate-only mode
    if args.validate_only:
        print(f"Skill '{args.skill}' is valid")
        return 0
    
    # Load input
    if args.file:
        input_file = Path(args.file)
        if not input_file.exists():
            print(f"Error: Input file not found: {args.file}", file=sys.stderr)
            return 1
        input_text = input_file.read_text(encoding='utf-8')
    else:
        input_text = args.text
    
    if args.verbose:
        print(f"Input length: {len(input_text)} characters", file=sys.stderr)
        print("Running skill...", file=sys.stderr)
    
    # Run skill
    try:
        output = run_skill(bundle, input_text)
    except Exception as e:
        print(f"Error running skill: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
    
    if args.verbose:
        print("✓ Skill completed", file=sys.stderr)
        print("\n--- Output ---", file=sys.stderr)
    
    # Print output to stdout
    print(output)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
