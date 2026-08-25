import os
import re
import sys
import requests
import yt_dlp

PROXY = os.getenv("PROXY_URL")
SHOWS_FILE = "shows.txt"

def load_urls():
    """Reads URLs from shows.txt. Creates one if it doesn't exist."""
    if not os.path.exists(SHOWS_FILE):
        print(f"{SHOWS_FILE} not found. Creating a default one.")
        with open(SHOWS_FILE, "w") as f:
            f.write("https://www.sonyliv.com/shows/indian-game-show-1790007836/season/2\n")
    
    with open(SHOWS_FILE, "r") as f:
        # Ignore blank lines and lines starting with #
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_episode_urls_from_season(season_url):
    print(f"Scraping season page for episodes: {season_url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        proxies = None
        if PROXY:
            req_proxy = PROXY.replace("socks5://", "socks5h://")
            proxies = {'http': req_proxy, 'https': req_proxy}
            
        response = requests.get(season_url, headers=headers, proxies=proxies, timeout=20)
        response.raise_for_status()
        html = response.text
        
        match = re.search(r'/shows/([^/]+-\d+)/', season_url)
        if not match:
            print("Could not parse show ID from season URL.")
            return []
            
        show_path = match.group(1)
        
        # BUG FIX: Broadened regex to catch URLs buried in JSON or irregular HTML tags
        pattern = rf'{show_path}/[^/\"\'>\s,]+-\d{{10}}'
        links = re.findall(pattern, html)
        
        episode_urls = []
        seen = set()
        for link in links:
            # Reconstruct the absolute URL cleanly
            full_link = f"https://www.sonyliv.com/shows/{link}?watch=true"
            if full_link not in seen:
                seen.add(full_link)
                episode_urls.append(full_link)
                
        print(f"Found {len(episode_urls)} total episodes.")
        
        # IMPROVEMENT 2: Keep only the 5 most recent episodes to save time & bandwidth
        recent_episodes = episode_urls[-5:]
        print(f"Limiting to the {len(recent_episodes)} most recent episodes.")
        return recent_episodes
        
    except Exception as e:
        print(f"Error scraping season page: {e}")
        return []

def extract_manifest_url(info):
    if info.get('url'):
        return info['url']
    formats = info.get('formats', [])
    if formats:
        for f in reversed(formats):
            if f.get('url'):
                return f['url']
    return None

def process_video_entry(info):
    title = info.get('title', 'Unknown Title')
    stream_url = extract_manifest_url(info)
    return title, stream_url

def extract_stream_data(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'all/best',
        'extract_flat': False,
        'ignoreerrors': True
    }
    
    if PROXY:
        ydl_opts['proxy'] = PROXY
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return None, None
        return process_video_entry(info)

def generate_m3u(urls, output_file="playlist.m3u"):
    playlist = ["#EXTM3U\n"]
    
    final_urls = []
    for url in urls:
        if "/season/" in url:
            final_urls.extend(get_episode_urls_from_season(url))
        else:
            final_urls.append(url)
            
    # IMPROVEMENT 4: Rich IPTV Variables
    logo = "https://origin-staticv2.sonyliv.com/UI_icons/sonyliv_new_revised_header_logo.png"
    group = "SonyLIV"
            
    for url in final_urls:
        try:
            print(f"\nProcessing: {url}")
            title, stream_url = extract_stream_data(url)
            
            if not stream_url:
                print(f"Skipping (no stream URL found): {url}")
                continue
                
            match = re.search(r'id=([0-9]+)', stream_url)
            if match:
                playback_id = match.group(1)
                final_url = f"{stream_url}|x-playback-session-id={playback_id}"
            else:
                final_url = stream_url 
                
            # IMPROVEMENT 4: Injecting standard IPTV tags for UI rendering
            playlist.append(f'#EXTINF:-1 group-title="{group}" tvg-logo="{logo}",{title}\n{final_url}\n')
            print(f"Success: {title}")
            
        except Exception as e:
            print(f"Error processing {url}: {e}")
            
    items_count = len(playlist) - 1
    
    if items_count == 0:
        print("\nFATAL ERROR: No streams were extracted. Failing the workflow.")
        sys.exit(1)
        
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(playlist)
        
    print(f"\nFinished! Added {items_count} streams to {output_file}")

if __name__ == "__main__":
    urls_to_process = load_urls()
    generate_m3u(urls_to_process)
