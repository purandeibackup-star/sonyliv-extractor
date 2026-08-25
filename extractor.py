import os
import re
import sys
import yt_dlp
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

# Suppress the SSL proxy warnings in the GitHub console
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROXY = os.getenv("PROXY_URL")
SHOWS_FILE = "shows.txt"

def load_urls():
    if not os.path.exists(SHOWS_FILE):
        print(f"{SHOWS_FILE} not found. Creating a default one.")
        with open(SHOWS_FILE, "w") as f:
            f.write("https://www.sonyliv.com/shows/indian-game-show-1790007836/season/2\n")
    
    with open(SHOWS_FILE, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_episodes_from_season(season_url):
    print(f"\nExtracting season episodes for: {season_url}")
    episode_urls = []
    
    # 1. Native yt-dlp extraction
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'ignoreerrors': True,
        'nocheckcertificate': True
    }
    if PROXY:
        ydl_opts['proxy'] = PROXY.replace("socks5://", "http://").replace("socks5h://", "http://")
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(season_url, download=False)
            if info and 'entries' in info:
                for entry in info['entries']:
                    if entry and entry.get('url'):
                        url = entry.get('url')
                        # Strict check: Must have a 10 digit ID and NO ad/garbage tracking names
                        if re.search(r'-\d{10}(?:\?|$)', url) and 'div-gpt' not in url and 'u002F' not in url:
                            if not url.startswith('http'):
                                url = f"https://www.sonyliv.com{url}"
                            episode_urls.append(url)
    except Exception as e:
        print(f"yt-dlp flat extraction error: {e}")

    # 2. Web Scraper Fallback if yt-dlp fails
    if not episode_urls:
        print("yt-dlp returned 0 episodes, falling back to web scraper...")
        try:
            import requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            proxies = None
            if PROXY:
                req_proxy = PROXY.replace("socks5://", "http://").replace("socks5h://", "http://")
                proxies = {'http': req_proxy, 'https': req_proxy}
                
            response = requests.get(season_url, headers=headers, proxies=proxies, timeout=20, verify=False)
            html = response.text
            
            match = re.search(r'/shows/([^/]+-\d{10})', season_url)
            if match:
                show_path = match.group(1)
                slugs = re.findall(r'"seoUrl":"([^"]+-\d{10})"', html)
                if not slugs:
                    raw_slugs = re.findall(r'([a-zA-Z0-9-]+-\d{10})', html)
                    # Filter out ads and unicode garbage
                    slugs = [s for s in raw_slugs if 'u002F' not in s and 'div-gpt' not in s]
                    
                for slug in slugs:
                    slug = slug.replace('\\u002F', '').replace('u002F', '')
                    # Final safety check before building the URL
                    if slug != show_path and 'div-gpt' not in slug and len(slug) > 15:
                        full_link = f"https://www.sonyliv.com/shows/{show_path}/{slug}?watch=true"
                        episode_urls.append(full_link)
        except Exception as e:
            print(f"Web scraper also failed: {e}")
            
    # Remove duplicates
    seen = set()
    unique_episodes = []
    for url in episode_urls:
        if url not in seen:
            seen.add(url)
            unique_episodes.append(url)
            
    if not unique_episodes:
        print("No episodes found. Treating as a single video URL.")
        return [season_url]
        
    print(f"Found {len(unique_episodes)} valid episodes.")
    recent_episodes = unique_episodes[-5:]
    print(f"Limiting to the {len(recent_episodes)} most recent episodes.")
    return recent_episodes

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
    print(f"Thread started: {url}")
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'all/best',
        'extract_flat': False,
        'ignoreerrors': True,
        'nocheckcertificate': True
    }
    
    if PROXY:
        ydl_opts['proxy'] = PROXY.replace("socks5://", "http://").replace("socks5h://", "http://")
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return url, None, None
        title, stream_url = process_video_entry(info)
        return url, title, stream_url

def generate_m3u(urls, output_file="playlist.m3u"):
    playlist = ["#EXTM3U\n"]
    
    final_urls = []
    for url in urls:
        if "/season/" in url:
            final_urls.extend(get_episodes_from_season(url))
        else:
            final_urls.append(url)
            
    logo = "https://origin-staticv2.sonyliv.com/UI_icons/sonyliv_new_revised_header_logo.png"
    group = "SonyLIV"
    
    extracted_data = []
    
    print(f"\nStarting parallel extraction for {len(final_urls)} streams...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(extract_stream_data, url): url for url in final_urls}
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                original_url, title, stream_url = future.result()
                if stream_url:
                    extracted_data.append((title, stream_url))
                else:
                    print(f"Skipping (no stream URL found): {url}")
            except Exception as e:
                print(f"Error processing {url}: {e}")
                
    extracted_data.sort(key=lambda x: x[0]) 

    for title, stream_url in extracted_data:
        match = re.search(r'id=([0-9]+)', stream_url)
        if match:
            playback_id = match.group(1)
            final_url = f"{stream_url}|x-playback-session-id={playback_id}"
        else:
            final_url = stream_url 
            
        playlist.append(f'#EXTINF:-1 group-title="{group}" tvg-logo="{logo}",{title}\n{final_url}\n')
        
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
