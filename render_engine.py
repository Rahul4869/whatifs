import os
import sys
import json
import argparse
import requests
import subprocess
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode_id", required=True)
    return parser.parse_args()

def fetch_episode_spec(webapp_url, webapp_token, episode_id):
    resp = requests.get(webapp_url, params={"token": webapp_token, "episode_id": episode_id}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise ValueError(f"Brain API Error: {data['error']}")
    return data

def report_status(webapp_url, webapp_token, payload):
    payload["token"] = webapp_token
    try:
        requests.post(webapp_url, json=payload, timeout=30)
    except Exception as e:
        print(f"Failed to report callback status: {e}")

def main():
    args = parse_args()
    episode_id = args.episode_id
    
    webapp_url = os.environ.get("WEBAPP_URL")
    webapp_token = os.environ.get("WEBAPP_TOKEN")
    
    start_time = datetime.utcnow()
    print(f"--- STARTING RENDER FOR {episode_id} ---")
    
    try:
        spec = fetch_episode_spec(webapp_url, webapp_token, episode_id)
        print(f"Loaded Spec: {spec.get('title')}")
        
        # Build base workspace
        os.makedirs("workspace", exist_ok=True)
        output_mp4 = f"workspace/{episode_id}_final.mp4"
        
        # Test synthetic frame assembly (Procedural base at 1440p)
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=0x0a0e17:s=2560x1440:d=10:r=30",
            "-vf", f"drawtext=text='What Ifs - {episode_id}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            output_mp4
        ]
        
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"Base render generated: {output_mp4}")
        
        end_time = datetime.utcnow()
        duration_min = round((end_time - start_time).total_seconds() / 60, 2)
        
        report_status(webapp_url, webapp_token, {
            "episode_id": episode_id,
            "render_started": start_time.isoformat(),
            "render_finished": end_time.isoformat(),
            "runner_minutes": duration_min,
            "yt_video_id": "TEST_PIPELINE_OK",
            "yt_status": "PROCESSED",
            "approval_state": "VERIFIED"
        })
        print("Pipeline run completed successfully.")
        
    except Exception as err:
        print(f"Pipeline error: {err}")
        report_status(webapp_url, webapp_token, {
            "episode_id": episode_id,
            "render_started": start_time.isoformat(),
            "render_finished": datetime.utcnow().isoformat(),
            "yt_status": "FAILED",
            "approval_state": f"ERROR: {str(err)}"
        })
        sys.exit(1)

if __name__ == "__main__":
    main()
