import os
import random
import json
import requests
import asyncio
import edge_tts
from groq import Groq
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
import moviepy.video.fx.all as vfx

# ==========================================
# 1. KONFIGURASI API KEY DARI ENVIRONMENT
# ==========================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
YOUTUBE_TOKEN = os.environ.get("YOUTUBE_TOKEN")

# Daftar negara
NEGARA_LIST = [
    "Jepang", "Islandia", "Italia", "Meksiko", "Mesir", 
    "Kanada", "Swiss", "India", "Brasil", "Turki", "Korea Selatan",
    "Belanda", "Norwegia", "Selandia Baru", "Maroko", "Argentina"
]

# ==========================================
# 2. FUNGSI GENERATE NASKAH (GROQ API - Llama 3.3)
# ==========================================
def get_script_from_groq(negara):
    print(f"[*] Meminta naskah untuk {negara} dari Groq API (Llama 3.3 70B)...")
    client = Groq(api_key=GROQ_API_KEY)
    
    prompt = f"""Kamu adalah pembuat konten YouTube Shorts profesional. Buatkan 3 fakta unik tentang kehidupan, tradisi, atau budaya di negara {negara}. 
    Naskah harus berbahasa Indonesia, santai, dan durasi jika dibaca maksimal 45 detik.
    Berikan 3 kata kunci bahasa Inggris (maksimal 3 kata per keyword) yang spesifik dan visual untuk mencari 3 video latar berbeda di Pexels yang relevan.
    Wajib balas HANYA dengan format JSON seperti ini:
    {{
        "judul": "Judul Shorts yang menarik",
        "deskripsi": "Deskripsi singkat video dan 3 hashtag",
        "naskah": "Teks naskah lengkap",
        "query_pexels": ["keyword 1", "keyword 2", "keyword 3"]
    }}"""

    # MENGGUNAKAN LLAMA 3.3 TERBARU
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile", 
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

# ==========================================
# 3. FUNGSI TEXT-TO-SPEECH (EDGE TTS)
# ==========================================
async def create_voiceover(text, output_filename="audio.mp3"):
    print("[*] Membuat Voiceover (Text-to-Speech)...")
    communicate = edge_tts.Communicate(text, "id-ID-GadisNeural")
    await communicate.save(output_filename)

# ==========================================
# 4. FUNGSI UNDUH MULTIPLE VIDEO (PEXELS API)
# ==========================================
def download_multiple_pexels_videos(queries):
    print(f"[*] Mencari video di Pexels untuk kata kunci: {queries}")
    headers = {"Authorization": PEXELS_API_KEY}
    downloaded_files = []
    
    for idx, query in enumerate(queries):
        url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=1"
        response = requests.get(url, headers=headers).json()
        
        if not response.get("videos"):
            print(f"[!] Video tidak ditemukan untuk query: '{query}'. Melewati...")
            continue
            
        video_files = response["videos"][0]["video_files"]
        hd_file = next((file for file in video_files if file["height"] >= 1080), video_files[0])
        video_url = hd_file["link"]
        
        output_filename = f"bg_{idx}.mp4"
        print(f"[*] Mengunduh video {idx+1}... ({query})")
        
        with requests.get(video_url, stream=True) as r:
            r.raise_for_status()
            with open(output_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        downloaded_files.append(output_filename)
        
    if not downloaded_files:
        raise Exception("Gagal mengunduh semua video Pexels.")
        
    return downloaded_files

# ==========================================
# 5. FUNGSI RENDER VIDEO GABUNGAN (MOVIEPY)
# ==========================================
def render_video(json_data, video_files):
    print("[*] Memulai proses render penggabungan video...")
    
    audio = AudioFileClip("audio.mp3")
    
    clips = []
    for file in video_files:
        print(f"[*] Memproses klip: {file}")
        clip = VideoFileClip(file).without_audio().resize((1080, 1920))
        clips.append(clip)
        
    gabungan_video = concatenate_videoclips(clips, method="compose")
    
    if gabungan_video.duration < audio.duration:
        print("[!] Gabungan video lebih pendek dari audio. Melakukan looping...")
        gabungan_video = gabungan_video.fx(vfx.loop, duration=audio.duration)
    else:
        gabungan_video = gabungan_video.subclip(0, audio.duration)
        
    gabungan_video = gabungan_video.set_audio(audio)
    
    try:
        txt_clip = TextClip(
            json_data["judul"], 
            fontsize=45, 
            color='white', 
            bg_color='rgba(0,0,0,0.5)', 
            method='caption', 
            size=(gabungan_video.w - 100, None)
        )
        txt_clip = txt_clip.set_pos(('center', 'center')).set_duration(gabungan_video.duration)
        final_video = CompositeVideoClip([gabungan_video, txt_clip])
    except Exception as e:
        print(f"[!] Gagal membuat teks (ImageMagick error), merender tanpa teks. Error: {e}")
        final_video = gabungan_video
    
    print("[*] Mengekspor hasil akhir (Ini akan memakan waktu)...")
    final_video.write_videofile(
        "hasil_shorts.mp4", 
        fps=24, 
        codec="libx264", 
        audio_codec="aac", 
        threads=2, 
        preset="ultrafast"
    )
    
    print("[*] Membersihkan file sementara...")
    for file in video_files:
        if os.path.exists(file):
            os.remove(file)
    if os.path.exists("audio.mp3"):
        os.remove("audio.mp3")
            
    print("[+] Video berhasil dibuat: hasil_shorts.mp4")

# ==========================================
# 6. FUNGSI UPLOAD YOUTUBE API
# ==========================================
def upload_to_youtube(video_file, judul, deskripsi):
    print("[*] Memulai proses upload ke YouTube...")
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials

    if not YOUTUBE_TOKEN:
        raise Exception("YOUTUBE_TOKEN tidak ditemukan di environment variables.")
        
    with open("token.json", "w") as f:
        f.write(YOUTUBE_TOKEN)
        
    try:
        creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/youtube.upload'])
        youtube = build('youtube', 'v3', credentials=creds)
        
        body = {
            'snippet': {
                'title': judul[:100], 
                'description': deskripsi,
                'tags': ['shorts', 'faktaunik', 'negaradunia', 'travel'],
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': 'private', # Default 'private' untuk uji coba (ubah ke 'public' saat sudah siap)
                'selfDeclaredMadeForKids': False
            }
        }
        
        media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype='video/mp4')
        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"[*] Uploading... {int(status.progress() * 100)}%")
                
        print(f"[+] Upload Selesai! ID Video: {response['id']}")
    finally:
        if os.path.exists("token.json"):
            os.remove("token.json")

# ==========================================
# 7. MAIN FUNCTION (EKSEKUSI UTAMA)
# ==========================================
async def main():
    negara = random.choice(NEGARA_LIST)
    print(f"=== MEMULAI BOT UNTUK NEGARA: {negara.upper()} ===")
    
    try:
        # Tahap 1: Generate Konten JSON
        konten = get_script_from_groq(negara)
        print("Data JSON dari Groq:", json.dumps(konten, indent=2))
        
        # Tahap 2: Buat Suara TTS
        await create_voiceover(konten["naskah"])
        
        # Tahap 3: Download 3 Video Berbeda
        downloaded_videos = download_multiple_pexels_videos(konten["query_pexels"])
        
        # Tahap 4: Render Video Final Gabungan
        render_video(konten, downloaded_videos)
        
        # Tahap 5: Upload ke YouTube
        deskripsi_lengkap = f"{konten['deskripsi']}\n\nFootage by Pexels\nScript by Llama-3.3 70B via Groq\nVoice by Edge-TTS\n#shorts"
        upload_to_youtube("hasil_shorts.mp4", konten["judul"], deskripsi_lengkap)
        
        print("=== SEMUA PROSES BERHASIL SELESAI ===")
        
    except Exception as e:
        print(f"[-] Terjadi kesalahan fatal: {e}")

if __name__ == "__main__":
    asyncio.run(main())
