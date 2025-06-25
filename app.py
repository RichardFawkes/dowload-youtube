from flask import Flask, render_template, request, jsonify, send_file
from pytubefix import YouTube
from pytubefix.cli import on_progress
import os
import subprocess
import tempfile
import uuid
from werkzeug.utils import secure_filename
import threading
import time

app = Flask(__name__)

# Configurações
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Status dos downloads
download_status = {}

def check_ffmpeg():
    """Verifica se o FFmpeg está disponível"""
    try:
        possible_paths = ['ffmpeg', 'C:\\ffmpeg\\bin\\ffmpeg.exe', 'C:\\Program Files\\FFmpeg\\bin\\ffmpeg.exe']
        for path in possible_paths:
            result = subprocess.run([path, '-version'], capture_output=True, check=True, timeout=10)
            if result.returncode == 0:
                return path
        return None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None

def progress_callback(stream, chunk, bytes_remaining):
    """Callback de progresso para o download"""
    total_size = stream.filesize
    bytes_downloaded = total_size - bytes_remaining
    percentage = (bytes_downloaded / total_size) * 100
    return percentage

@app.route('/')
def index():
    return render_template('index.html')

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
        
        # Obtém streams disponíveis
        streams = []
        
        # Streams progressivos (vídeo + áudio juntos)
        progressive_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
        for stream in progressive_streams:
            streams.append({
                'resolution': stream.resolution,
                'type': 'progressive',
                'size': f"{stream.filesize / (1024*1024):.1f} MB" if stream.filesize else 'N/A',
                'quality': f"{stream.resolution} (Vídeo + Áudio)"
            })
        
        # Streams adaptativos (apenas vídeo)
        if check_ffmpeg():
            adaptive_video = yt.streams.filter(adaptive=True, only_video=True, file_extension='mp4').order_by('resolution').desc()
            for stream in adaptive_video:
                if stream.resolution not in [s['resolution'] for s in streams]:
                    streams.append({
                        'resolution': stream.resolution,
                        'type': 'adaptive',
                        'size': f"{stream.filesize / (1024*1024):.1f} MB" if stream.filesize else 'N/A',
                        'quality': f"{stream.resolution} HD (Requer FFmpeg)"
                    })
        
        # Streams de áudio apenas
        audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        if audio_stream:
            streams.append({
                'resolution': 'audio',
                'type': 'audio',
                'size': f"{audio_stream.filesize / (1024*1024):.1f} MB" if audio_stream.filesize else 'N/A',
                'quality': f"Apenas Áudio ({audio_stream.abr})"
            })
        
        return jsonify({
            'video_info': video_info,
            'streams': streams,
            'ffmpeg_available': check_ffmpeg() is not None
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao obter informações do vídeo: {str(e)}'}), 400

@app.route('/download', methods=['POST'])
def download_video():
    """Inicia o download do vídeo"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        resolution = data.get('resolution', '').strip()
        
        if not url or not resolution:
            return jsonify({'error': 'URL e resolução são obrigatórias'}), 400
        
        # Gera ID único para o download
        download_id = str(uuid.uuid4())
        download_status[download_id] = {
            'status': 'iniciando',
            'progress': 0,
            'message': 'Iniciando download...',
            'file_path': None
        }
        
        # Inicia download em thread separada
        thread = threading.Thread(target=download_worker, args=(download_id, url, resolution))
        thread.daemon = True
        thread.start()
        
        return jsonify({'download_id': download_id})
        
    except Exception as e:
        return jsonify({'error': f'Erro ao iniciar download: {str(e)}'}), 400

def download_worker(download_id, url, resolution):
    """Worker para fazer o download em background"""
    try:
        download_status[download_id]['message'] = 'Conectando ao YouTube...'
        
        # Cria objeto YouTube
        yt = YouTube(url)
        
        # Nome seguro do arquivo
        safe_filename = "".join(c for c in yt.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        download_status[download_id]['message'] = 'Obtendo streams...'
        
        if resolution == 'audio':
            # Download apenas áudio
            download_status[download_id]['message'] = 'Baixando áudio...'
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            if stream:
                file_path = os.path.join(DOWNLOAD_FOLDER, f"{safe_filename}_audio.mp4")
                stream.download(output_path=DOWNLOAD_FOLDER, filename=f"{safe_filename}_audio.mp4")
                download_status[download_id] = {
                    'status': 'concluido',
                    'progress': 100,
                    'message': 'Download concluído!',
                    'file_path': file_path
                }
            else:
                raise Exception("Stream de áudio não encontrado")
                
        elif resolution in ['1080p', '720p'] and check_ffmpeg():
            # Download HD com FFmpeg
            download_status[download_id]['message'] = 'Baixando vídeo HD...'
            
            video_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True, res=resolution).first()
            audio_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_audio=True).order_by('abr').desc().first()
            
            if video_stream and audio_stream:
                # Download vídeo
                video_temp = os.path.join(DOWNLOAD_FOLDER, f"{download_id}_video.mp4")
                video_stream.download(output_path=DOWNLOAD_FOLDER, filename=f"{download_id}_video.mp4")
                
                download_status[download_id]['message'] = 'Baixando áudio...'
                download_status[download_id]['progress'] = 50
                
                # Download áudio
                audio_temp = os.path.join(DOWNLOAD_FOLDER, f"{download_id}_audio.mp4")
                audio_stream.download(output_path=DOWNLOAD_FOLDER, filename=f"{download_id}_audio.mp4")
                
                download_status[download_id]['message'] = 'Combinando vídeo e áudio...'
                download_status[download_id]['progress'] = 75
                
                # Combina com FFmpeg
                output_file = os.path.join(DOWNLOAD_FOLDER, f"{safe_filename}_HD_{resolution}.mp4")
                ffmpeg_path = check_ffmpeg()
                
                cmd = [
                    ffmpeg_path, 
                    '-i', video_temp,
                    '-i', audio_temp,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-y',
                    output_file
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                # Remove arquivos temporários
                if os.path.exists(video_temp):
                    os.remove(video_temp)
                if os.path.exists(audio_temp):
                    os.remove(audio_temp)
                
                if result.returncode == 0:
                    download_status[download_id] = {
                        'status': 'concluido',
                        'progress': 100,
                        'message': f'Download HD {resolution} concluído!',
                        'file_path': output_file
                    }
                else:
                    raise Exception("Erro ao combinar vídeo e áudio")
            else:
                raise Exception(f"Stream {resolution} não encontrado")
                
        else:
            # Download progressivo
            download_status[download_id]['message'] = f'Baixando em {resolution}...'
            
            stream = yt.streams.filter(progressive=True, file_extension='mp4', res=resolution).first()
            if stream:
                file_path = os.path.join(DOWNLOAD_FOLDER, f"{safe_filename}_{resolution}.mp4")
                stream.download(output_path=DOWNLOAD_FOLDER, filename=f"{safe_filename}_{resolution}.mp4")
                download_status[download_id] = {
                    'status': 'concluido',
                    'progress': 100,
                    'message': f'Download {resolution} concluído!',
                    'file_path': file_path
                }
            else:
                raise Exception(f"Stream {resolution} não encontrado")
                
    except Exception as e:
        download_status[download_id] = {
            'status': 'erro',
            'progress': 0,
            'message': f'Erro: {str(e)}',
            'file_path': None
        }

@app.route('/status/<download_id>')
def get_download_status(download_id):
    """Retorna o status do download"""
    if download_id in download_status:
        return jsonify(download_status[download_id])
    else:
        return jsonify({'error': 'Download não encontrado'}), 404

@app.route('/download_file/<download_id>')
def download_file(download_id):
    """Baixa o arquivo para o usuário"""
    if download_id in download_status and download_status[download_id]['file_path']:
        file_path = download_status[download_id]['file_path']
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
    return jsonify({'error': 'Arquivo não encontrado'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 