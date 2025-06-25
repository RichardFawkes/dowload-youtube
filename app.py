from flask import Flask, render_template, request, jsonify, send_file
from pytubefix import YouTube
from pytubefix.cli import on_progress
import os
import tempfile
import uuid
import threading
import time
import subprocess
import shutil

app = Flask(__name__)

# Diretório para downloads
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Status dos downloads
download_status = {}

def create_youtube_object(url):
    """Cria objeto YouTube com configurações anti-bot"""
    try:
        # Primeira tentativa: com use_po_token
        return YouTube(url, use_po_token=True)
    except:
        try:
            # Segunda tentativa: sem po_token mas com client web
            return YouTube(url, client='WEB')
        except:
            # Terceira tentativa: configuração padrão
            return YouTube(url)

def check_ffmpeg():
    """Verifica se FFmpeg está disponível"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def format_duration(seconds):
    """Formata duração em segundos para HH:MM:SS"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"
    return f"{int(minutes):02d}:{int(secs):02d}"

def format_number(num):
    """Formata números grandes (views)"""
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return str(num)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_video_info', methods=['POST'])
def get_video_info():
    """Obtém informações do vídeo"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        # Cria objeto YouTube com anti-bot
        yt = create_youtube_object(url)
        
        # Obtém informações básicas
        video_info = {
            'title': yt.title,
            'author': yt.author,
            'length': yt.length,
            'thumbnail': yt.thumbnail_url,
            'views': yt.views,
            'description': yt.description[:200] + '...' if len(yt.description or '') > 200 else yt.description
        }
        
        # Verifica se FFmpeg está disponível
        ffmpeg_available = check_ffmpeg()
        
        # Obtém streams disponíveis
        streams = []
        
        if ffmpeg_available:
            # Com FFmpeg: streams adaptivos (HD)
            video_streams = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by('resolution').desc()
            for stream in video_streams:
                if stream.resolution in ['1080p', '720p', '480p', '360p']:
                    streams.append({
                        'resolution': stream.resolution,
                        'type': 'adaptive',
                        'size': f"{stream.filesize / (1024*1024):.1f} MB" if stream.filesize else 'N/A',
                        'quality': f"{stream.resolution} HD (Vídeo + Áudio)"
                    })
        
        # Streams progressivos (funcionam sem FFmpeg)
        progressive_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
        for stream in progressive_streams:
            streams.append({
                'resolution': stream.resolution,
                'type': 'progressive',
                'size': f"{stream.filesize / (1024*1024):.1f} MB" if stream.filesize else 'N/A',
                'quality': f"{stream.resolution} (Vídeo + Áudio)"
            })
        
        # Stream de áudio apenas
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
            'ffmpeg_available': ffmpeg_available
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao obter informações do vídeo: {str(e)}'}), 400

@app.route('/start_download', methods=['POST'])
def start_download():
    """Inicia o download do vídeo"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        resolution = data.get('resolution', '').strip()
        
        if not url or not resolution:
            return jsonify({'error': 'URL e resolução são obrigatórias'}), 400
        
        # Gera ID único para o download
        download_id = str(uuid.uuid4())
        
        # Inicializa status
        download_status[download_id] = {
            'status': 'starting',
            'progress': 0,
            'filename': '',
            'error': None
        }
        
        # Inicia download em thread separada
        thread = threading.Thread(
            target=download_video_thread,
            args=(download_id, url, resolution)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({'download_id': download_id})
        
    except Exception as e:
        return jsonify({'error': f'Erro ao iniciar download: {str(e)}'}), 400

def download_video_thread(download_id, url, resolution):
    """Thread para download do vídeo"""
    try:
        # Atualiza status
        download_status[download_id]['status'] = 'downloading'
        
        # Cria objeto YouTube com anti-bot
        yt = create_youtube_object(url)
        
        # Nome seguro do arquivo
        safe_filename = "".join(c for c in yt.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        if resolution == 'audio':
            # Download apenas áudio
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            filename = f"{safe_filename}_audio.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            stream.download(output_path=DOWNLOAD_DIR, filename=filename)
            
        elif resolution in ['1080p', '720p'] and check_ffmpeg():
            # Download HD com FFmpeg
            video_stream = yt.streams.filter(adaptive=True, file_extension='mp4', res=resolution, only_video=True).first()
            audio_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_audio=True).order_by('abr').desc().first()
            
            if not video_stream or not audio_stream:
                raise Exception(f"Stream {resolution} não encontrado")
            
            # Arquivos temporários
            video_temp = os.path.join(DOWNLOAD_DIR, f"temp_video_{download_id}.mp4")
            audio_temp = os.path.join(DOWNLOAD_DIR, f"temp_audio_{download_id}.mp4")
            
            # Download streams
            download_status[download_id]['status'] = 'downloading_video'
            video_stream.download(output_path=DOWNLOAD_DIR, filename=f"temp_video_{download_id}.mp4")
            
            download_status[download_id]['status'] = 'downloading_audio'
            audio_stream.download(output_path=DOWNLOAD_DIR, filename=f"temp_audio_{download_id}.mp4")
            
            # Combina com FFmpeg
            download_status[download_id]['status'] = 'processing'
            filename = f"{safe_filename}_{resolution}.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', video_temp,
                '-i', audio_temp,
                '-c', 'copy',
                filepath
            ]
            
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            
            # Remove arquivos temporários
            os.remove(video_temp)
            os.remove(audio_temp)
            
        else:
            # Download progressivo
            stream = yt.streams.filter(progressive=True, file_extension='mp4', res=resolution).first()
            if not stream:
                raise Exception(f"Stream {resolution} não encontrado")
            
            filename = f"{safe_filename}_{resolution}.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            stream.download(output_path=DOWNLOAD_DIR, filename=filename)
        
        # Sucesso
        download_status[download_id].update({
            'status': 'completed',
            'progress': 100,
            'filename': filename,
            'filepath': filepath
        })
        
    except Exception as e:
        download_status[download_id].update({
            'status': 'error',
            'error': str(e)
        })

@app.route('/download_status/<download_id>')
def get_download_status(download_id):
    """Retorna status do download"""
    if download_id not in download_status:
        return jsonify({'error': 'Download não encontrado'}), 404
    
    return jsonify(download_status[download_id])

@app.route('/download_file/<download_id>')
def download_file(download_id):
    """Faz download do arquivo"""
    if download_id not in download_status:
        return jsonify({'error': 'Download não encontrado'}), 404
    
    status = download_status[download_id]
    if status['status'] != 'completed':
        return jsonify({'error': 'Download não concluído'}), 400
    
    filepath = status['filepath']
    if not os.path.exists(filepath):
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    
    return send_file(filepath, as_attachment=True, download_name=status['filename'])

# Limpeza automática de arquivos antigos (executar periodicamente)
def cleanup_old_files():
    """Remove arquivos antigos"""
    try:
        current_time = time.time()
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(filepath):
                # Remove arquivos com mais de 1 hora
                if current_time - os.path.getmtime(filepath) > 3600:
                    os.remove(filepath)
    except Exception as e:
        print(f"Erro na limpeza: {e}")

# Executar limpeza a cada 30 minutos
def schedule_cleanup():
    while True:
        time.sleep(1800)  # 30 minutos
        cleanup_old_files()

# Inicia thread de limpeza
cleanup_thread = threading.Thread(target=schedule_cleanup)
cleanup_thread.daemon = True
cleanup_thread.start()

if __name__ == '__main__':
    app.run(debug=True) 