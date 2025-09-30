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

COOKIE_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'youtube_cookies.txt')

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
    
    a = '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'
    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s-%(title)s.%(ext)s'),
        'retries': 5,
        'quiet': True,
        'no_warnings': True,
        'cachedir': False,
        'cookie': a,
        #'http_headers': {
        #    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 6_0 like Mac OS X) AppleWebKit/536.26 (KHTML, like Gecko) Version/6.0 Mobile/10A5376e Safari/8536.25',
        #    'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        #}
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