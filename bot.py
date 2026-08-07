import os
import random
import json
import requests
import asyncio
import edge_tts
from groq import Groq
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx.all import crop

# 1. Konfigurasi API dari GitHub Secrets
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

# Daftar Negara Acak
NEGARA_LIST = ["Jepang", "Islandia", "Italia", "Meksiko", "Mesir", "Kanada", "Swiss", "India"]

def get_script_from_groq(negara):
    """Meminta Groq API untuk membuat naskah JSON"""
    print(f"[*] Menulis naskah untuk {negara} menggunakan Groq...")
    client = Groq(api_key=GROQ_API_KEY)
    
    prompt = f"""Kamu adalah pembuat konten YouTube Shorts. Buatkan 3 fakta unik tentang kehidupan atau budaya di negara {negara}. 
    Naskah berbahasa Indonesia, durasi baca maksimal 45 detik.
    Berikan juga 1 kata kunci bahasa Inggris pendek yang spesifik dan visual untuk mencari video di Pexels (contoh: "Tokyo neon night", "Iceland snow").
    Wajib balas HANYA dengan format JSON:
    {{
        "judul": "Judul Shorts",
        "naskah": "Teks naskah lengkap",
        "query_pexels": "kata kunci"
    }}"""

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="mixtral-8x7b-32768",
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

async def create_voiceover(text, output_filename="audio.mp3"):
    """Mengubah teks menjadi suara menggunakan Edge TTS"""
    print("[*] Membuat Voiceover...")
    communicate = edge_tts.Communicate(text, "id-ID-GadisNeural")
    await communicate.save(output_filename)

def download_pexels_video(query, output_filename="background.mp4"):
    """Mengunduh video vertikal dari Pexels"""
    print(f"[*] Mencari video Pexels untuk: {query}...")
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=1"
    
    response = requests.get(url, headers=headers).json()
    if not response.get("videos"):
        raise Exception("Video tidak ditemukan di Pexels.")
    
    # Ambil link video dengan kualitas HD
    video_files = response["videos"][0]["video_files"]
    hd_file = next((file for file in video_files if file["height"] >= 1080), video_files[0])
    video_url = hd_file["link"]
    
    print("[*] Mengunduh video...")
    with requests.get(video_url, stream=True) as r:
        r.raise_for_status()
        with open(output_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

def render_video(json_data):
    """Menggabungkan Video, Audio, dan Teks Judul menggunakan MoviePy"""
    print("[*] Memulai proses render video...")
    
    # Load Audio & Video
    audio = AudioFileClip("audio.mp3")
    video = VideoFileClip("background.mp4")
    
    # Potong video agar sesuai durasi audio (loop jika video kurang panjang)
    if video.duration < audio.duration:
        print("[!] Peringatan: Video asli lebih pendek dari audio, memotong sesuai batas video.")
        audio = audio.subclip(0, video.duration)
    else:
        video = video.subclip(0, audio.duration)
        
    video = video.set_audio(audio)
    
    # Tambahkan Teks Judul di tengah (Opsional)
    txt_clip = TextClip(json_data["judul"], fontsize=50, color='white', bg_color='black', method='caption', size=(video.w - 100, None))
    txt_clip = txt_clip.set_pos('center').set_duration(video.duration)
    
    # Gabungkan
    final_video = CompositeVideoClip([video, txt_clip])
    
    print("[*] Mengekspor hasil akhir (Ini akan memakan waktu)...")
    # Setting CPU threads agar tidak crash di GitHub Actions
    final_video.write_videofile("hasil_shorts.mp4", fps=24, codec="libx264", audio_codec="aac", threads=2, preset="ultrafast")
    print("[+] Video berhasil dibuat: hasil_shorts.mp4")

async def main():
    negara = random.choice(NEGARA_LIST)
    
    try:
        # 1. Generate Konten
        konten = get_script_from_groq(negara)
        print("Data JSON dari Groq:", konten)
        
        # 2. Buat Suara
        await create_voiceover(konten["naskah"])
        
        # 3. Unduh Video
        download_pexels_video(konten["query_pexels"])
        
        # 4. Render Video
        render_video(konten)
        
        # (Tahap 5: Upload ke YouTube akan dipanggil di sini jika menggunakan Google API Client)
        # upload_to_youtube("hasil_shorts.mp4", konten["judul"], konten["naskah"])
        
    except Exception as e:
        print(f"[-] Terjadi kesalahan: {e}")

if __name__ == "__main__":
    asyncio.run(main())
