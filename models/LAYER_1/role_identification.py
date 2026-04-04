"""
Role Identification Module

Uses the identify-call-roles skill to automatically identify speaker roles
in call transcripts and replace generic SPEAKER_A/SPEAKER_B labels.
"""

import sys
import json
from pathlib import Path

# Add skill runtime and skills to path
SKILL_ROOT = Path(__file__).parent.parent / "skill_implementation"
sys.path.insert(0, str(SKILL_ROOT / "skill_runtime"))
sys.path.insert(0, str(SKILL_ROOT / "skill_runtime" / "backends"))
sys.path.insert(0, str(SKILL_ROOT / "skills" / "identify-call-roles"))

# Import required modules
try:
    from skill import get_identify_call_roles_skill_bundle
    from llama_cpp import Llama
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print(f"Make sure llama-cpp-python is installed in the calltone environment")
    raise


def run_skill_simple(bundle: dict, input_text: str) -> str:
    """
    Simple skill runner using llama-cpp-python directly.
    
    Args:
        bundle: Skill bundle dict
        input_text: Input text to process
        
    Returns:
        Generated output text
    """
    model_path = bundle['model_dir']
    
    # Initialize model
    llm = Llama(
        model_path=model_path,
        n_ctx=4096,
        n_threads=8,
        n_gpu_layers=-1,  # Use GPU if available
        verbose=False,
    )
    
    # Format prompt with llama-3.1 chat template
    system_prompt = bundle['system_prompt']
    user_prompt = bundle['user_prompt_template'].format(input_text=input_text)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    # Generate
    decoding = bundle['decoding']
    response = llm.create_chat_completion(
        messages=messages,
        temperature=decoding.get('temperature', 0.0),
        top_p=decoding.get('top_p', 1.0),
        max_tokens=decoding.get('max_tokens', 1024),
        stop=decoding.get('stop'),
    )
    
    output = response['choices'][0]['message']['content']
    return output.strip()


def format_transcript_for_skill(json_data: dict, max_segments: int = 30) -> str:
    """
    Format diarization JSON into readable transcript for role identification.
    
    Args:
        json_data: Diarization JSON output
        max_segments: Maximum number of segments to include (to avoid context overflow)
        
    Returns:
        Formatted transcript string
    """
    segments = json_data.get('transcript', json_data.get('segments', []))
    
    # Take first N segments (usually enough to identify roles)
    segments_to_use = segments[:max_segments]
    
    lines = []
    for seg in segments_to_use:
        speaker = seg['speaker']
        text = seg.get('text', '').strip()
        if text:
            lines.append(f"{speaker}: {text}")
    
    return "\n".join(lines)


def identify_speaker_roles(json_path: str) -> dict[str, str]:
    """
    Identify speaker roles using the identify-call-roles skill.
    
    Args:
        json_path: Path to diarization JSON file
        
    Returns:
        Dict mapping speaker labels to roles, e.g.:
        {"SPEAKER_A": "Customer Service Agent", "SPEAKER_B": "Customer"}
        
    Raises:
        ValueError: If role identification fails
    """
    print("\n" + "="*80)
    print("ROLE IDENTIFICATION")
    print("="*80)
    
    # Load diarization JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    
    # Format transcript for skill
    transcript_text = format_transcript_for_skill(json_data)
    print(f"Analyzing first {len(transcript_text.splitlines())} segments...\n")
    
    # Load skill bundle
    skill_bundle = get_identify_call_roles_skill_bundle()
    
    # Run skill
    print("Running identify-call-roles skill...")
    try:
        result_json_str = run_skill_simple(skill_bundle, transcript_text)
        
        # Parse JSON result
        result = json.loads(result_json_str)
        
        # Extract role mappings
        agent_speaker = result.get('agent_speaker', 'UNKNOWN')
        customer_speaker = result.get('customer_speaker', 'UNKNOWN')
        confidence = result.get('confidence', 0.0)
        reason = result.get('reason_short', '')
        
        print(f"✓ Role identification complete!")
        print(f"  Agent: {agent_speaker}")
        print(f"  Customer: {customer_speaker}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Reason: {reason}\n")
        
        # Create role mapping
        role_map = {}
        if agent_speaker != 'UNKNOWN':
            role_map[agent_speaker] = "Customer Service Agent"
        if customer_speaker != 'UNKNOWN':
            role_map[customer_speaker] = "Customer"
        
        return role_map
        
    except json.JSONDecodeError as e:
        print(f"⚠ Warning: Failed to parse skill output as JSON: {e}")
        print(f"Raw output: {result_json_str[:200]}...")
        return {}
    except Exception as e:
        print(f"⚠ Warning: Role identification failed: {e}")
        return {}


def apply_roles_to_outputs(json_path: str, txt_path: str, role_map: dict[str, str]):
    """
    Apply identified roles to both JSON and TXT outputs.
    
    Args:
        json_path: Path to diarization JSON file
        txt_path: Path to diarization TXT file
        role_map: Dict mapping speaker labels to roles
    """
    if not role_map:
        print("⚠ No roles identified, keeping original speaker labels")
        return
    
    print("Applying roles to outputs...")
    
    # Update JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    
    # Update speaker_summary keys
    if 'speaker_summary' in json_data:
        new_summary = {}
        for speaker, data in json_data['speaker_summary'].items():
            role = role_map.get(speaker, speaker)
            data['role'] = role  # Add role field
            new_summary[role] = data
        json_data['speaker_summary'] = new_summary
    
    # Update transcript segments
    segments = json_data.get('transcript', json_data.get('segments', []))
    for seg in segments:
        speaker = seg['speaker']
        if speaker in role_map:
            seg['role'] = role_map[speaker]
            seg['speaker'] = role_map[speaker]
    
    # Update call_metadata
    if 'call_metadata' in json_data:
        json_data['call_metadata']['roles_identified'] = True
        json_data['call_metadata']['role_mapping'] = role_map
    
    # Save updated JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # Update TXT
    with open(txt_path, 'r', encoding='utf-8') as f:
        txt_content = f.read()
    
    # Update header to show roles identified
    if "Speakers : 2  (SPEAKER_A, SPEAKER_B)" in txt_content:
        # Get role names for header
        roles_list = list(role_map.values())
        roles_str = ", ".join(roles_list)
        txt_content = txt_content.replace(
            "Speakers : 2  (SPEAKER_A, SPEAKER_B)",
            f"Speakers : 2  ({roles_str})"
        )
    
    # Replace speaker labels in TXT
    for speaker, role in role_map.items():
        # Replace in headers like "[00:06→00:08]  SPEAKER_A"
        txt_content = txt_content.replace(f"  {speaker}", f"  {role}")
        # Replace in summary sections
        txt_content = txt_content.replace(f"  {speaker}\n", f"  {role}\n")
    
    # Save updated TXT
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(txt_content)
    
    print(f"✓ Roles applied to JSON and TXT outputs\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python role_identification.py <json_file> <txt_file>")
        sys.exit(1)
    
    json_file = sys.argv[1]
    txt_file = sys.argv[2]
    
    # Identify roles
    roles = identify_speaker_roles(json_file)
    
    # Apply to outputs
    if roles:
        apply_roles_to_outputs(json_file, txt_file, roles)
