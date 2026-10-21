import os
import json
import requests
import fal_client
import time

# --- ENVIRONMENT VARIABLES ---
# The fal_client automatically detects the FAL_KEY from the environment
MAX_HERO_CLIPS = 8

def fetch_episode_spec(episode_id, webapp_url, token):
    """Fetches the JSON specification from the Google Apps Script Web App."""
    print(f"Fetching spec for {episode_id}...")
    response = requests.get(f"{webapp_url}?episode_id={episode_id}&token={token}")
    if response.status_code != 200:
        raise Exception(f"Failed to fetch spec: {response.text}")
    return response.json()

def run_preflight_auditor(spec):
    """Enforces fiscal control by capping Kling clips to MAX_HERO_CLIPS."""
    print("\n=== PREFLIGHT AUDITOR ===")
    script_data = spec.get("script", {})
    sections = script_data.get("sections", [])
    
    hero_count = 0
    for beat in sections:
        if beat.get("hero_motion") is True:
            hero_count += 1
            if hero_count > MAX_HERO_CLIPS:
                print(f"[AUDIT] Budget cap reached. Downgrading Beat {beat.get('beat')} to FLUX still.")
                beat["hero_motion"] = False
                
    print(f"[AUDIT] Cleared: {min(hero_count, MAX_HERO_CLIPS)} Kling clips authorized out of {hero_count} requested.\n")
    return spec

def generate_flux_anchor(prompt):
    """Generates the 8K photorealistic base image via FLUX.1 Ultra."""
    print(f"Generating FLUX anchor: {prompt[:60]}...")
    try:
        result = fal_client.subscribe(
            "fal-ai/flux-pro/v1.1-ultra",
            arguments={
                "prompt": prompt + ", 35mm optical anamorphic, 8k cinematic, photorealistic documentary style", 
                "aspect_ratio": "16:9"
            },
        )
        return result.get("images")[0].get("url")
    except Exception as e:
        print(f"FLUX Generation Error: {e}")
        return None

def generate_kling_motion(image_url, motion_prompt):
    """Animates the FLUX anchor using Kling V1.5."""
    print(f"Generating Kling motion: {motion_prompt[:60]}...")
    try:
        result = fal_client.subscribe(
            "fal-ai/kling-video/v1.5/i2v",
            arguments={
                "image_url": image_url,
                "prompt": motion_prompt,
                "duration": "5",
                "aspect_ratio": "16:9"
            },
        )
        return result.get("video", {}).get("url")
    except Exception as e:
        print(f"Kling Generation Error: {e}")
        return None

def execute_visual_pipeline(spec):
    """Main orchestrator for the two-step visual engine."""
    sections = spec.get("script", {}).get("sections", [])
    rendered_assets = []

    for beat in sections:
        beat_num = beat.get("beat")
        print(f"\n--- Processing Beat {beat_num} ---")
        
        # Step 1: Always generate the FLUX Anchor
        visual_prompt = beat.get("visual_prompt") or beat.get("motion_prompt") or "Cinematic science scene"
        anchor_url = generate_flux_anchor(visual_prompt)
        
        if not anchor_url:
            print(f"Skipping Beat {beat_num} due to missing anchor.")
            continue
            
        # Step 2: Upgrade to Kling if authorized by Auditor
        if beat.get("hero_motion") is True:
            motion_url = generate_kling_motion(anchor_url, beat.get("motion_prompt"))
            rendered_assets.append({"beat": beat_num, "type": "video", "url": motion_url or anchor_url})
        else:
            rendered_assets.append({"beat": beat_num, "type": "image", "url": anchor_url})
            
        # Small delay to respect rate limits
        time.sleep(2)
        
    print("\n=== VISUAL PIPELINE COMPLETE ===")
    return rendered_assets

if __name__ == "__main__":
    ep_id = os.environ.get("EPISODE_ID")
    webapp_url = os.environ.get("WEBAPP_URL")
    token = os.environ.get("WEBAPP_TOKEN")
    
    if not ep_id:
        print("Test execution. No EPISODE_ID found. Exiting.")
    else:
        raw_spec = fetch_episode_spec(ep_id, webapp_url, token)
        audited_spec = run_preflight_auditor(raw_spec)
        assets = execute_visual_pipeline(audited_spec)
        
        # Output JSON map for FFmpeg assembly stage
        output_file = f"assets_{ep_id}.json"
        with open(output_file, "w") as f:
            json.dump(assets, f, indent=2)
        print(f"Asset map saved to {output_file}")
