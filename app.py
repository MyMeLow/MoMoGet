import os
import json
import time
import re
import traceback
import threading
from flask import Flask, request, jsonify, render_template, send_from_directory, url_for
from yt_dlp import YoutubeDL, DownloadError
from yt_dlp.utils import ExtractorError

app = Flask(__name__, 
            static_folder='static',
            template_folder='templates')


DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

CLEANUP_DELAY_SECONDS = 600 


_download_status = {}

status_lock = threading.Lock()

def delete_file_after_delay(filepath, delay_seconds):
    """
    指定された秒数後にファイルを削除する非同期処理。
    """
    app.logger.info(f"Cleanup scheduled for: {os.path.basename(filepath)} in {delay_seconds} seconds.")
    time.sleep(delay_seconds)
    
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            app.logger.info(f"Cleanup successful: {os.path.basename(filepath)} was deleted.")
        else:
            app.logger.warning(f"Cleanup target not found (already deleted?): {os.path.basename(filepath)}")
            
    except Exception as e:
        app.logger.error(f"Error during file cleanup for {os.path.basename(filepath)}: {str(e)}")

def run_download_in_thread(video_url, ydl_opts, video_id):
    """
    yt-dlpのダウンロード処理を別スレッドで実行する。
    エラー発生時はステータスを更新する。
    """
    downloaded_filepath_local = None 

    def postprocessor_hook(d):
        """yt-dlpのコールバック。ダウンロードの進捗をグローバル辞書に保存する。"""
        nonlocal downloaded_filepath_local
        
        progress_data = {
            'status': d['status'],
            'progress': d.get('_percent_str', '0%').strip(),
            'downloaded_bytes': d.get('downloaded_bytes'),
            'total_bytes': d.get('total_bytes', d.get('total_bytes_estimate')),
            'eta': d.get('_eta_str', 'N/A').strip(),
            'speed': d.get('_speed_str', 'N/A').strip(),
            'error_message': None # エラーメッセージ用
        }
        with status_lock:
            _download_status[video_id] = progress_data
            
        if d['status'] == 'finished':
            downloaded_filepath_local = d['filename']
            app.logger.info(f"Download finished in thread. Final filepath: {downloaded_filepath_local}")

    try:
        app.logger.info(f"Starting download thread for ID: {video_id}")
        
        ydl_opts_thread = ydl_opts.copy()
        ydl_opts_thread['progress_hooks'] = [postprocessor_hook]

        with YoutubeDL(ydl_opts_thread) as ydl:
            ydl.download([video_url])
            
        with status_lock:
            _download_status[video_id] = {'status': 'completed', 'progress': '100%'}

    except Exception as e:
        error_msg = str(e)
        app.logger.error(f"Download thread failed for ID {video_id}: {traceback.format_exc()}")
        with status_lock:
            _download_status[video_id] = {
                'status': 'error',
                'progress': '0%',
                'error_message': error_msg
            }

@app.route('/')
def index():
    """メインダウンロードページ"""
    return render_template('index.html')

@app.route('/how_to_use')
def how_to_use():
    """使い方ページ"""
    return render_template('how_to_use.html')

@app.route('/progress/<video_id>', methods=['GET'])
def get_progress(video_id):
    """クライアントからのポーリングに応じて、現在の進捗状況を返す"""
    with status_lock:
        status_data = _download_status.get(video_id, {'status': 'initializing', 'progress': '0%'})
        
    return jsonify(status_data)

@app.route('/download', methods=['POST'])
def download():
    """動画のダウンロード処理を実行し、ダウンロードリンクを返す"""
    video_url = request.form.get('url')
    
    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s-%(title)s.%(ext)s'),
        'retries': 5,
        'quiet': True,
        'no_warnings': True,
        'cachedir': False,
        'cookies' : 'cookies.txt',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36',
            'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        }
    }
    
    try:
        app.logger.info(f"Attempting download metadata extraction for URL: {video_url}")
        
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            video_id = info_dict.get('id')
            video_title = info_dict.get('title')
            
            if not video_id:
                raise Exception("動画情報の取得に失敗")

            with status_lock:
                _download_status[video_id] = {
                    'status': 'extracting', 
                    'progress': '0%', 
                    'title': video_title
                }
            
            download_thread = threading.Thread(
                target=run_download_in_thread, 
                args=(video_url, ydl_opts, video_id)
            )
            download_thread.daemon = True
            download_thread.start()
        
            return jsonify({
                'status': 'progress',
                'video_id': video_id,
                'message': 'ダウンロード開始'
            })

    except DownloadError as e:
        error_msg = str(e)
        match = re.search(r'ERROR: (.+?)(?:$|\n)', error_msg)
        display_message = match.group(1) if match else "URLが無効か、アクセスできない"
        app.logger.error(f"DownloadError for URL {video_url}: {error_msg}")
        return jsonify({
            'status': 'error',
            'message': f"エラー: {display_message}"
        }), 500
    
    except ExtractorError:
        app.logger.error(f"ExtractorError for URL {video_url}: {traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': '別のURLを試してね'
        }), 500

    except Exception as e:
        app.logger.error(f"Unexpected error during yt-dlp library execution: {traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': f"予期せぬエラーが発生した: {str(e)}"
        }), 500


@app.route('/check_completion/<video_id>', methods=['GET'])
def check_completion(video_id):
    """
    リアルタイムダウンロードが完了したかを確認し、完了していたらリンクを返す。
    """
    with status_lock:
        current_status = _download_status.get(video_id)

    if not current_status:
        return jsonify({'status': 'in_progress', 'message': 'サーバーが動画IDを認識できません。'}), 202

    if current_status['status'] == 'completed':
        try:
            files = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(f"{video_id}-")]
            
            if not files:
                return jsonify({'status': 'waiting_for_file', 'message': 'ファイルがまだディスクに書き込まれていません。'}), 202
                
            files.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True)
            downloaded_filepath = os.path.join(DOWNLOAD_DIR, files[0])

            filename_only = os.path.basename(downloaded_filepath)
            filename_without_ext = os.path.splitext(filename_only)[0]
            if '-' in filename_without_ext:
                extracted_title = '-'.join(filename_without_ext.split('-')[1:])
            else:
                extracted_title = filename_without_ext 
            
            download_filename = os.path.basename(downloaded_filepath)
            download_link = url_for('download_file', filename=download_filename, _external=True)

            cleanup_thread = threading.Thread(
                target=delete_file_after_delay, 
                args=(downloaded_filepath, CLEANUP_DELAY_SECONDS)
            )
            cleanup_thread.daemon = True
            cleanup_thread.start()
            
            with status_lock:
                if video_id in _download_status:
                    del _download_status[video_id]

            return jsonify({
                'status': 'success',
                'title': extracted_title,
                'download_link': download_link
            })
        
        except Exception as e:
            app.logger.error(f"Error processing final file for {video_id}: {traceback.format_exc()}")
            return jsonify({
                'status': 'error',
                'message': f"ファイルの最終処理中にエラーが発生: {str(e)}"
            }), 500

    elif current_status['status'] == 'error':
        error_message = current_status.get('error_message', '詳細不明のエラー。')
        with status_lock:
            del _download_status[video_id]
            
        return jsonify({
            'status': 'error',
            'message': f"ダウンロードスレッドで致命的なエラーが発生: {error_message}"
        }), 500
    
    # まだダウンロードが進行中
    return jsonify({'status': 'in_progress', 'message': 'ダウンロード継続中...'}), 202


@app.route('/download_file/<filename>')
def download_file(filename):
    """
    ファイルをダウンロードディレクトリから送信する。
    """
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO) 
    app.run()