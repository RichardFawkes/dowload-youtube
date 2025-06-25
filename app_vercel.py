from flask import Flask, render_template, request, jsonify, redirect, url_for
from pytubefix import YouTube
import os
import tempfile
import uuid
import threading
import time

app = Flask(__name__)

# Status dos downloads (em memória para Vercel)
download_status = {}

@app.route('/')
def index():
    return render_template('index_vercel.html')

@app.route('/get_video_info', methods=['POST'])
def get_video_info():
    """Obtém informações do vídeo sem baixar"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        # Cria objeto YouTube
        yt = YouTube(url)
        
        # Obtém informações básicas
        video_info = {
            'title': yt.title,
            'author': yt.author,
            'length': yt.length,
            'thumbnail': yt.thumbnail_url,
            'views': yt.views,
            'description': yt.description[:200] + '...' if len(yt.description or '') > 200 else yt.description
        }
        
        # Obtém apenas streams progressivos (sem FFmpeg)
        streams = []
        
        # Streams progressivos (vídeo + áudio juntos)
        progressive_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
        for stream in progressive_streams:
            streams.append({
                'resolution': stream.resolution,
                'type': 'progressive',
                'size': f"{stream.filesize / (1024*1024):.1f} MB" if stream.filesize else 'N/A',
                'quality': f"{stream.resolution} (Vídeo + Áudio)",
                'download_url': stream.url
            })
        
        # Stream de áudio apenas
        audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        if audio_stream:
            streams.append({
                'resolution': 'audio',
                'type': 'audio',
                'size': f"{audio_stream.filesize / (1024*1024):.1f} MB" if audio_stream.filesize else 'N/A',
                'quality': f"Apenas Áudio ({audio_stream.abr})",
                'download_url': audio_stream.url
            })
        
        return jsonify({
            'video_info': video_info,
            'streams': streams,
            'ffmpeg_available': False  # Sempre False na Vercel
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao obter informações do vídeo: {str(e)}'}), 400

@app.route('/get_download_url', methods=['POST'])
def get_download_url():
    """Retorna URL direta para download (Vercel-friendly)"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        resolution = data.get('resolution', '').strip()
        
        if not url or not resolution:
            return jsonify({'error': 'URL e resolução são obrigatórias'}), 400
        
        # Cria objeto YouTube
        yt = YouTube(url)
        
        if resolution == 'audio':
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        else:
            stream = yt.streams.filter(progressive=True, file_extension='mp4', res=resolution).first()
        
        if stream:
            # Nome seguro do arquivo
            safe_filename = "".join(c for c in yt.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            
            return jsonify({
                'download_url': stream.url,
                'filename': f"{safe_filename}_{resolution}.mp4",
                'title': yt.title,
                'size': f"{stream.filesize / (1024*1024):.1f} MB" if stream.filesize else 'N/A'
            })
        else:
            return jsonify({'error': f'Stream {resolution} não encontrado'}), 400
            
    except Exception as e:
        return jsonify({'error': f'Erro ao obter URL de download: {str(e)}'}), 400

if __name__ == '__main__':
    app.run(debug=True) 