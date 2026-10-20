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

def get_audio_duration(file_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def generate_audio_beats(script_data, workspace_dir):
    print("--- GENERATING AUDIO BEATS ---")
    sections = script_data.get("sections", [])
    if not sections:
        print("Warning: No 'sections' found in script.")
        return []

    audio_plan = []
    for i, section in enumerate(sections):
        beat_num = section.get("beat", i+1)
        text = section.get("narration", "")
        
        if not text: continue
        
        out_file = os.path.join(workspace_dir, f"beat_{beat_num}.mp3")
        print(f"Synthesizing Beat {beat_num}...")
        
        # Using Microsoft's Neural API for high-fidelity documentary voiceover
        tts_cmd = [
            "edge-tts",
            "--voice", "en-US-ChristopherNeural",
            "--rate", "-5%", # Slowed slightly for dramatic pacing
            "--text", text,
            "--write-media", out_file
        ]
        subprocess.run(tts_cmd, check=True)
        
        duration = get_audio_duration(out_file)
        print(f"Beat {beat_num} Audio: {duration:.2f} seconds")
        
        audio_plan.append({
            "beat": beat_num,
            "file": out_file,
            "duration": duration,
            "text": text
        })
        
    return audio_plan

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
        
        workspace = "workspace"
        os.makedirs(workspace, exist_ok=True)
        
        # PHASE 1: AUDIO SYNTHESIS
        script_json = spec.get("script", {})
        if isinstance(script_json, str):
            try:
                script_json = json.loads(script_json)
            except:
                script_json = {"sections": []}
                
        audio_plan = generate_audio_beats(script_json, workspace)
        total_duration = sum(beat["duration"] for beat in audio_plan)
        print(f"Total Voiceover Duration: {total_duration:.2f} seconds")
        
        output_mp4 = os.path.join(workspace, f"{episode_id}_audio_test.mp4")
        
        if audio_plan:
            # Stitch all beats into a seamless master audio track
            concat_list = os.path.join(workspace, "concat.txt")
            with open(concat_list, "w") as f:
                for beat in audio_plan:
                    f.write(f"file '{os.path.basename(beat['file'])}'\n")
            
            master_audio = os.path.join(workspace, "master_audio.mp3")
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", master_audio], check=True)
            
            # Generate video matching exact length of the new audio track
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=0x0a0e17:s=2560x1440:d={total_duration}:r=30",
                "-i", master_audio,
                "-vf", f"drawtext=text='What Ifs - {episode_id} - Audio Sync Complete':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                output_mp4
            ]
            subprocess.run(ffmpeg_cmd, check=True)
            print(f"Audio master video generated: {output_mp4}")
        
        end_time = datetime.utcnow()
        duration_min = round((end_time - start_time).total_seconds() / 60, 2)
        
        report_status(webapp_url, webapp_token, {
            "episode_id": episode_id,
            "render_started": start_time.isoformat(),
            "render_finished": end_time.isoformat(),
            "runner_minutes": duration_min,
            "yt_video_id": "AUDIO_SYNC_OK",
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
