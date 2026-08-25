import os
import re
import urllib.request
import yt_dlp

# You can put season URLs or direct episode URLs here
URLS = [
    "https://www.sonyliv.com/shows/indian-game-show-1790007836/season/2"
]

PROXY = os.getenv("PROXY_URL")

def get_episode_urls_from_season(season_url):
    """Scrapes the season page HTML to find all individual episode URLs."""
    print(f"Scraping season page for episodes: {season_url}")
    try:
        # We use a standard browser User-Agent so SonyLIV doesn't block the request
        req = urllib.request.Request(season_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        html = urllib.request.urlopen(req).read().decode('utf-8')
        
        # 1. Extract the show name and ID from the season URL
        # e.g., 'indian-game-show-1790007836'
        match = re.search(r'/shows/([^/]+-\d+)/', season_url)
        if not match:
            print("Could not parse show ID from season URL.")
            return []
            
        show_path = match.group(1)
        
        # 2. Find all episode links on the page that end in a 10-digit ID
        # Matches paths like: /shows/indian-game-show-1790007836/a-star-studded-start-1090540220
        pattern = rf'/shows/{show_path}/[a-zA-Z0-9-]+-\d{{10}}'
        links = re.findall(pattern, html)
        
        # 3. Deduplicate links while keeping them in the order they appeared on the page
        episode_urls = []
        seen = set()
        for link in links:
            if link not in seen:
                seen.add(link)
                episode_urls.append(f"https://www.sonyliv.com{link}?watch=true")
                
        print(f"Found {len(episode_urls)} episodes on the season page.")
        return episode_urls
        
    except Exception as e:
        print(f"Error scraping season page: {e}")
        return []

def extract_manifest_url(info):
    """Safely finds the manifest URL (.mpd or .m3u8) across formats."""
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
    
    # Check if the URL is a season. If it is, scrape the episodes out of it.
    final_urls = []
    for url in urls:
        if "/season/" in url:
            final_urls.extend(get_episode_urls_from_season(url))
        else:
            final_urls.append(url)
            
    for url in final_urls:
        try:
            print(f"\nProcessing: {url}")
            title, stream_url = extract_stream_data(url)
            
            if not stream_url:
                print(f"Skipping (no stream URL found): {url}")
                continue
                
            # Regex to find 'id=xxxxxxxxxxxx' inside the hdnea token
            match = re.search(r'id=([0-9]+)', stream_url)
            if match:
                playback_id = match.group(1)
                final_url = f"{stream_url}|x-playback-session-id={playback_id}"
            else:
                final_url = stream_url 
                
            playlist.append(f"#EXTINF:-1,{title}\n{final_url}\n")
            print(f"Success: {title}")
            
        except Exception as e:
            print(f"Error processing {url}: {e}")
            
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(playlist)
        
    items_count = len(playlist) - 1
    print(f"\nFinished! Added {items_count} streams to {output_file}")

if __name__ == "__main__":
    generate_m3u(URLS)
