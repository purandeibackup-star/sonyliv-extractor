import os
import re
import sys
import time
import yt_dlp

PROXY = os.getenv("PROXY_URL")
SHOWS_FILE = "shows.txt"
PLAYLIST_FILE = "playlist.m3u"

def load_shows():
    if not os.path.exists(SHOWS_FILE):
        with open(SHOWS_FILE, "w") as f:
            f.write("https://www.sonyliv.com/shows/indian-game-show-1790007836 | SonyLIV\n")
    
    shows = []
    with open(SHOWS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            
            if "|" in line:
                url, group = line.split("|", 1)
                shows.append((url.strip(), group.strip()))
            else:
                shows.append((line, "SonyLIV"))
    return shows

def resolve_latest_episode(url):
    """If a general Show URL is provided, scans the page and returns the newest episode."""
    # If it's already a direct episode link, skip scanning
    if "?watch=" in url or "/episode/" in url:
        return url
        
    print(f"Scanning show for latest episode: {url}")
    ydl_opts = {'quiet': True, 'extract_flat': True, 'ignoreerrors': True}
    if PROXY: ydl_opts['proxy'] = PROXY
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and 'entries' in info:
                valid_urls = []
                for entry in info['entries']:
                    if not entry: continue
                    ep_url = entry.get('url', '')
                    
                    # Filter out garbage Ad tags
                    if 'div-gpt' in ep_url or 'seoUrl' in ep_url: continue
                    
                    # Ensure it's a real episode by looking for the 10-digit ID
                    match = re.search(r'-(\d{10})(?:\?|$)', ep_url)
                    if match:
                        if ep_url.startswith('/'):
                            ep_url = f"https://www.sonyliv.com{ep_url}"
                        valid_urls.append((int(match.group(1)), ep_url))
                        
                if valid_urls:
                    # Sort numerically by ID descending (newest episodes have highest IDs)
                    valid_urls.sort(key=lambda x: x[0], reverse=True)
                    latest_url = valid_urls[0][1]
                    if "?watch=true" not in latest_url:
                        latest_url += "?watch=true"
                    print(f"  -> Found newest episode ID: {valid_urls[0][0]}")
                    return latest_url
    except Exception as e:
        print(f"  -> Error resolving season: {e}")
        
    return url

def check_if_update_needed(resolved_shows):
    if os.getenv("GITHUB_EVENT_NAME") == "push":
        print("Detected push to repository. Forcing update.")
        return True

    if not os.path.exists(PLAYLIST_FILE):
        print("No playlist found. Update required.")
        return True
        
    with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Check if a new episode was released
    for resolved_url, _ in resolved_shows:
        match = re.search(r'-(\d{10})(?:\?|$)', resolved_url)
        if match:
            ep_id = match.group(1)
            # If the newest episode ID isn't in our playlist, we must update!
            if ep_id not in content:
                print(f"New episode detected (ID: {ep_id}). Forcing update.")
                return True
                
    # If no new episode, check if the current token is expiring
    exp_times = re.findall(r'exp=(\d+)', content)
    if not exp_times:
        return True
        
    current_time = time.time()
    for exp in exp_times:
        time_left = int(exp) - current_time
        if time_left < 2100:  # 35 minutes
            print(f"Token expires in {int(time_left/60)} minutes. Update required.")
            return True
            
    print("No new episodes found & tokens are still valid. Skipping.")
    return False

def clean_title(title):
    title = re.sub(r'\s*-\s*SonyLIV$', '', title, flags=re.IGNORECASE)
    return title.strip()

def extract_stream_data(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestvideo+bestaudio/best',
        'extractor_args': {'sonyliv': {'formats': 'dash'}},
        'ignoreerrors': True,
        'extract_flat': False,
        'socket_timeout': 30,
    }
    
    if PROXY:
        ydl_opts['proxy'] = PROXY

    for attempt in range(1, 5):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    title = clean_title(info.get('title', 'Unknown Title'))
                    stream_url = None
                    
                    formats = info.get('formats', [])
                    for f in reversed(formats):
                        f_url = f.get('url', '')
                        if '.mpd' in f_url:
                            stream_url = f_url
                            break
                            
                    if not stream_url:
                        general_url = info.get('url', '')
                        if '.mpd' in general_url:
                            stream_url = general_url
                            
                    if stream_url:
                        return title, stream_url
        except Exception as e:
            print(f"  [Attempt {attempt}/4] Extraction failed: {e}")
            
        print(f"  Retrying in 5 seconds...")
        time.sleep(5)
        
    return None, None

def generate_m3u():
    raw_shows = load_shows()
    if not raw_shows:
        sys.exit(1)
        
    resolved_shows = []
    print("\nChecking for latest episodes...")
    for url, group in raw_shows:
        resolved_shows.append((resolve_latest_episode(url), group))
        
    if not check_if_update_needed(resolved_shows):
        sys.exit(0)
        
    playlist = ["#EXTM3U\n"]
    logo = "https://origin-staticv2.sonyliv.com/UI_icons/sonyliv_new_revised_header_logo.png"
    
    success_count = 0
    fail_count = 0
    
    print(f"\nStarting extraction for {len(resolved_shows)} stream(s)...\n" + "-"*40)
    
    for url, group_name in resolved_shows:
        print(f"Processing: {url}\n  -> Group: {group_name}")
        title, stream_url = extract_stream_data(url)
        
        if not stream_url:
            print(f"  [X] Failed to find MPD stream URL.\n")
            fail_count += 1
            continue
            
        # Extract ID for tracking new episodes and playback session
        ep_id = "unknown"
        ep_match = re.search(r'-(\d{10})(?:\?|$)', url)
        if ep_match:
            ep_id = ep_match.group(1)

        match = re.search(r'id=([0-9]+)', stream_url)
        if match:
            playback_id = match.group(1)
            final_url = f"{stream_url}|x-playback-session-id={playback_id}"
        else:
            path_match = re.search(r'/DASH/([a-fA-F0-9]{32})/', stream_url)
            if path_match:
                playback_id = path_match.group(1)
                final_url = f"{stream_url}|x-playback-session-id={playback_id}"
            else:
                final_url = f"{stream_url}|x-playback-session-id=98404716139163545924947790596008"
            
        # We save the Episode ID inside the playlist so the script knows what episode it currently has
        playlist.append(f'#EXTINF:-1 group-title="{group_name}" tvg-logo="{logo}" tvg-id="{ep_id}",{title}\n{final_url}\n')
        success_count += 1
        print(f"  [V] Success: Added '{title}'\n")
        
    print("-"*40)
    print(f"Extraction Summary: {success_count} succeeded, {fail_count} failed.")
    
    if success_count == 0:
        print("\nFATAL ERROR: No MPD streams were extracted. Failing the workflow.")
        sys.exit(1)
        
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        f.writelines(playlist)
        
    print(f"\nPlaylist successfully saved to {PLAYLIST_FILE}")

if __name__ == "__main__":
    generate_m3u()
