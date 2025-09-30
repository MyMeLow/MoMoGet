// ハンバーガーメニューの開閉機能
function toggleMenu() {
    const nav = document.getElementById('nav-menu');
    const toggle = document.getElementById('menu-toggle');
    nav.classList.toggle('open');
    toggle.classList.toggle('open');
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('download-form');
    const urlInput = document.getElementById('video-url');
    const resultArea = document.getElementById('result-area');
    const loadingOverlay = document.getElementById('loading-overlay');
    const button = form.querySelector('button');

    // 進捗表示関連のDOM要素
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressMessage = document.getElementById('progress-message');
    const progressDetail = document.getElementById('progress-detail');
    const initialLoadingMessage = document.getElementById('initial-loading-message');
    const loaderSpinner = document.getElementById('loader-spinner'); // スピナーを追加

    // プレイヤーコンテナ
    const videoPlayerContainer = document.getElementById('video-player-container');


    // SweetAlert2 Toast の設定
    const Toast = Swal.mixin({
        toast: true,
        position: 'top-end',
        showConfirmButton: false,
        timer: 3000,
        timerProgressBar: true,
        customClass: {
            popup: 'momo-toast'
        },
        didOpen: (toast) => {
            toast.onmouseenter = Swal.stopTimer;
            toast.onmouseleave = Swal.resumeTimer;
        }
    });

    const toggleLoading = (isVisible, isProgress = false) => {
        if (isVisible) {
            loadingOverlay.classList.remove('hidden');
            button.setAttribute('disabled', 'true');
            
            if (isProgress) {
                progressContainer.classList.remove('hidden');
                initialLoadingMessage.classList.add('hidden');
                loaderSpinner.classList.remove('hidden'); 
                button.textContent = '進行中...';
            } else {
                progressContainer.classList.add('hidden');
                initialLoadingMessage.classList.remove('hidden');
                initialLoadingMessage.textContent = '動画情報を解析中...';
                loaderSpinner.classList.remove('hidden');
                button.textContent = '解析中...';
            }
            
        } else {
            loadingOverlay.classList.add('hidden');
            button.removeAttribute('disabled');
            button.textContent = 'GET!';
            progressContainer.classList.add('hidden');
            loaderSpinner.classList.add('hidden');
        }
    };

    const handleSuccess = (data) => {
        videoPlayerContainer.innerHTML = ''; 
        
        const videoElement = document.createElement('video');
        videoElement.src = data.download_link;
        videoElement.controls = true;
        videoElement.autoplay = false;
        videoElement.classList.add('download-video-player');
        
        videoElement.setAttribute('type', 'video/mp4'); 
        videoElement.onerror = () => {
             videoPlayerContainer.innerHTML = `<p class="text-sm text-red-500 font-bold">再生に失敗しました。このブラウザでは動画形式がサポートされていないかファイルが利用不可です。</p>`;
        };

        videoPlayerContainer.appendChild(videoElement);
        
        document.getElementById('result-status').textContent = 'ステータス: 成功 (ダウンロード準備完了)';
        document.getElementById('result-title').textContent = `動画タイトル: ${data.title}`;
        document.getElementById('result-filesize').textContent = `${Math.ceil(600 / 60)} 分後にリンクは失効します！`; 

        const linkElement = document.getElementById('result-link');
        linkElement.href = data.download_link;
        linkElement.textContent = `${data.title} のダウンロードリンク`;
        linkElement.download = data.title ? `${data.title}.mp4` : 'video.mp4';

        resultArea.classList.remove('hidden');

        Toast.fire({
            icon: 'success',
            title: '成功',
            text: 'ダウンロードリンクとプレイヤーが準備完了',
            timer: 5000 
        });
        
        createSparkleBurst(window.innerWidth / 2, window.innerHeight / 2);
    };

    // ダウンロード失敗時の演出
    const handleError = (message) => {
        Toast.fire({
            icon: 'error',
            title: '失敗...',
            text: message || '予期せぬエラーが発生'
        });
        resultArea.classList.add('hidden');
    };


    let progressInterval = null;

    const startPolling = (video_id) => {
        if (progressInterval) {
            clearInterval(progressInterval);
        }

        progressInterval = setInterval(async () => {
            try {
                const response = await fetch(`/progress/${video_id}`);
                
                if (!response.ok) {
                    clearInterval(progressInterval);
                    handleError(`進捗確認でエラーが発生しました (${response.status})。`);
                    toggleLoading(false);
                    return;
                }

                const data = await response.json();

                const status = data.status;
                const progressText = data.progress || '0%';
                let progressPercentage = parseFloat(progressText.replace('%', '')) || 0;

                if (status === 'postprocessing') {
                    progressPercentage = 100;
                }
                progressBar.style.width = `${progressPercentage}%`;

                let detailText = '';
                if (data.speed && data.eta) {
                    detailText = `速度: ${data.speed} / 残り時間: ${data.eta}`;
                }

                progressDetail.textContent = detailText;
                
                toggleLoading(true, true); 

                switch (status) {
                    case 'extracting':
                        progressMessage.textContent = `動画情報を解析中... ${data.title ? '(' + data.title + ')' : ''}`;
                        break;
                    case 'downloading':
                        progressMessage.textContent = `ダウンロード中... ${progressText}`;
                        break;
                    case 'postprocessing':
                        progressMessage.textContent = 'ファイル処理中 (統合・変換)...';
                        break;
                    case 'completed':
                        clearInterval(progressInterval);
                        progressMessage.textContent = 'ダウンロード完了。ファイルの準備中...';
                        initialLoadingMessage.textContent = 'ファイルの最終準備中...';
                        progressContainer.classList.add('hidden');
                        initialLoadingMessage.classList.remove('hidden');
                        loaderSpinner.classList.remove('hidden');
                        checkCompletion(video_id);
                        break;
                    case 'error':
                        clearInterval(progressInterval);
                        handleError(data.error_message || 'ダウンロード中にエラーが発生しました。');
                        toggleLoading(false);
                        break;
                    default:
                        progressMessage.textContent = '初期化中...';
                }

            } catch (error) {
                console.error('Progress polling error:', error);
            }
        }, 1000); 
    };
    

    const checkCompletion = async (video_id) => {
        let completionCheckInterval = null;

        completionCheckInterval = setInterval(async () => {
            try {
                const response = await fetch(`/check_completion/${video_id}`);
                const data = await response.json();
                
                if (data.status === 'success') {
                    clearInterval(completionCheckInterval);
                    toggleLoading(false);
                    handleSuccess(data);

                } else if (data.status === 'error') {
                    clearInterval(completionCheckInterval);
                    handleError(data.message);
                    toggleLoading(false);
                }

            } catch (error) {
                console.error('Completion check error:', error);
                clearInterval(completionCheckInterval);
                handleError('ファイルの最終準備中にネットワークエラーが発生しました。');
                toggleLoading(false);
            }
        }, 2000); 
    };

    // フォーム送信処理
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        if (!urlInput.value.startsWith('http')) {
             handleError('URLの形式が正しくない');
             return;
        }

        if (progressInterval) {
            clearInterval(progressInterval);
        }

        videoPlayerContainer.innerHTML = ''; // プレイヤーをリセット
        toggleLoading(true, false); 
        resultArea.classList.add('hidden'); 

        try {
            const formData = new FormData(form);
            
            const response = await fetch('/download', {
                method: 'POST',
                body: new URLSearchParams(formData)
            });

            const data = await response.json();

            if (data.status === 'progress') {
                startPolling(data.video_id);
            } else if (data.status === 'error') {
                handleError(data.message);
                toggleLoading(false);
            } else {
                handleError('サーバーからの応答が不正');
                toggleLoading(false);
            }

        } catch (error) {
            console.error('Fetch error:', error);
            handleError('サーバーとの通信中に問題が発生');
            toggleLoading(false);
        }
    });

    function createSparkleBurst(x, y) {
        const numSparkles = 10; 
        for (let i = 0; i < numSparkles; i++) {
            const sparkle = document.createElement('div');
            sparkle.className = 'sparkle-effect';
            
            sparkle.style.background = 'var(--momo-gold-accent)';
            sparkle.style.width = '5px';
            sparkle.style.height = '5px';
            sparkle.style.borderRadius = '50%';
            sparkle.style.position = 'absolute';
            
            const tx = (Math.random() - 0.5) * 80; 
            const ty = - (80 + Math.random() * 80);

            const randomX = x + (Math.random() - 0.5) * 40;
            const randomY = y + (Math.random() - 0.5) * 40;

            sparkle.style.left = `${randomX}px`;
            sparkle.style.top = `${randomY}px`;
            
            sparkle.style.setProperty('--tx', `${tx}px`);
            sparkle.style.setProperty('--ty', `${ty}px`);
            
            const delay = Math.random() * 0.15;
            const duration = 0.8 + Math.random() * 0.4;
            
            sparkle.style.animation = `sparkle-fly ${duration}s cubic-bezier(0.1, 0.7, 1.0, 0.1) forwards`;
            sparkle.style.animationDelay = `${delay}s`;

            document.body.appendChild(sparkle);
            
            setTimeout(() => {
                sparkle.remove();
            }, (duration + delay) * 1000);
        }
    }
    
    const style = document.createElement('style');
    style.textContent = `
        @keyframes sparkle-fly {
            0% { 
                transform: translate(0, 0) scale(1); 
                opacity: 1;
            }
            100% { 
                transform: translate(var(--tx), var(--ty)) scale(0.5); 
                opacity: 0; 
            }
        }
    `;
    document.head.appendChild(style);


    const initialSparkleCount = Math.floor(Math.random() * 5) + 5; 
    for (let i = 0; i < initialSparkleCount; i++) {
        const x = Math.random() * window.innerWidth;
        const y = Math.random() * window.innerHeight * 0.5; 
        createSparkleBurst(x, y);
    }
});