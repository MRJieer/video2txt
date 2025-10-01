import os
import yt_dlp
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class VideoProcessor:
    """视频处理器，使用yt-dlp下载和转换视频"""
    
    def __init__(self):
        self.ydl_opts = {
            'format': 'bestaudio/best',  # 优先下载最佳音频源
            'outtmpl': '%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                # 直接在提取阶段转换为单声道 16k（空间小且稳定）
                'preferredcodec': 'm4a',
                'preferredquality': '192'
            }],
            # 全局FFmpeg参数：单声道 + 16k 采样率 + faststart
            'postprocessor_args': ['-ac', '1', '-ar', '16000', '-movflags', '+faststart'],
            'prefer_ffmpeg': True,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,  # 强制只下载单个视频，不下载播放列表
        }
    
    async def download_and_convert(self, url: str, output_dir: Path) -> tuple[str, str]:
        # 【修复1】函数内所有内容需缩进4个空格（从这里开始）
        """
        下载视频（或读取本地文件）并转换为m4a格式
        
        Args:
            url: 视频链接 或 本地MP4文件路径（如 D:/test.mp4）
            output_dir: 输出目录
            
        Returns:
            转换后的音频文件路径、视频标题
        """
        try:
            # 创建输出目录
            output_dir.mkdir(exist_ok=True)
            
            # 生成唯一的文件名（保持原逻辑）
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_template = str(output_dir / f"audio_{unique_id}.%(ext)s")
            
            # -------------------------- 新增：判断是否为本地MP4文件 --------------------------
            is_local_file = False
            local_video_path = ""
            # 检查输入的"url"是否为本地文件路径（支持 Windows 路径如 D:/xx.mp4、C:\\xx.mp4）
            if (os.path.exists(url) and url.lower().endswith(('.mp4', '.mov', '.avi', '.flv'))):
                is_local_file = True
                local_video_path = url  # 确认是本地视频文件
                video_title = os.path.basename(local_video_path)  # 用文件名作为视频标题
                logger.info(f"检测到本地视频文件: {local_video_path}，标题: {video_title}")
            # ------------------------------------------------------------------------------

            # 更新yt-dlp选项（保持原逻辑）
            ydl_opts = self.ydl_opts.copy()
            ydl_opts['outtmpl'] = output_template

            if not is_local_file:
                # 原逻辑：处理URL视频（保持不变）
                logger.info(f"开始下载视频: {url}")
                import asyncio
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, False)
                    video_title = info.get('title', 'unknown')
                    expected_duration = info.get('duration') or 0
                    logger.info(f"视频标题: {video_title}")
                    await asyncio.to_thread(ydl.download, [url])
            else:
                # -------------------------- 新增：处理本地视频文件 --------------------------
                # 1. 提取本地MP4的音频（用FFmpeg直接转换，无需yt-dlp）
                logger.info(f"开始提取本地视频音频: {local_video_path}")
                # 目标音频路径（m4a格式，单声道16k采样率，兼容Whisper）
                audio_file = str(output_dir / f"audio_{unique_id}.m4a")
                # 构造FFmpeg命令：提取音频+转换格式+标准化参数
                import subprocess, shlex
                ffmpeg_cmd = (
                    f"ffmpeg -y -i {shlex.quote(local_video_path)} "  # 输入本地MP4
                    "-vn "  # 不处理视频流，只提取音频
                    "-ac 1 "  # 转为单声道
                    "-ar 16000 "  # 16k采样率（Whisper推荐）
                    "-c:a aac "  # 音频编码
                    "-b:a 192k "  # 音频比特率
                    "-movflags +faststart "  # 优化文件结构
                    f"{shlex.quote(audio_file)}"  # 输出音频文件
                )
                # 执行FFmpeg命令（同步执行，本地文件处理较快）
                subprocess.check_call(ffmpeg_cmd, shell=True)
                logger.info(f"本地视频音频提取完成: {audio_file}")
                # 2. 获取本地视频时长（用于后续校验）
                try:
                    probe_cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {shlex.quote(local_video_path)}"
                    out = subprocess.check_output(probe_cmd, shell=True).decode().strip()
                    expected_duration = float(out) if out else 0.0
                except Exception as e:
                    expected_duration = 0.0
                    logger.warning(f"获取本地视频时长失败: {e}")
                # --------------------------------------------------------------------------

            # -------------------------- 原逻辑：查找生成的音频文件（保持不变） --------------------------
            if not is_local_file:  # 只有URL下载才需要查找文件，本地处理已明确生成m4a
                audio_file = str(output_dir / f"audio_{unique_id}.m4a")
                if not os.path.exists(audio_file):
                    for ext in ['webm', 'mp4', 'mp3', 'wav']:
                        potential_file = str(output_dir / f"audio_{unique_id}.{ext}")
                        if os.path.exists(potential_file):
                            audio_file = potential_file
                            break
                    else:
                        raise Exception("未找到下载的音频文件")

            # -------------------------- 原逻辑：音频时长校验（保持不变） --------------------------
            try:
                import subprocess, shlex
                probe_cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {shlex.quote(audio_file)}"
                out = subprocess.check_output(probe_cmd, shell=True).decode().strip()
                actual_duration = float(out) if out else 0.0
            except Exception as _:
                actual_duration = 0.0

            if expected_duration and actual_duration and abs(actual_duration - expected_duration) / expected_duration > 0.1:
                logger.warning(
                    f"音频时长异常，期望{expected_duration}s，实际{actual_duration}s，尝试重封装修复…"
                )
                try:
                    fixed_path = str(output_dir / f"audio_{unique_id}_fixed.m4a")
                    fix_cmd = f"ffmpeg -y -i {shlex.quote(audio_file)} -vn -c:a aac -b:a 160k -movflags +faststart {shlex.quote(fixed_path)}"
                    subprocess.check_call(fix_cmd, shell=True)
                    audio_file = fixed_path
                    out2 = subprocess.check_output(probe_cmd.replace(shlex.quote(audio_file.rsplit('.',1)[0]+'.m4a'), shlex.quote(audio_file)), shell=True).decode().strip()
                    actual_duration2 = float(out2) if out2 else 0.0
                    logger.info(f"重封装完成，新时长≈{actual_duration2:.2f}s")
                except Exception as e:
                    logger.error(f"重封装失败：{e}")

            logger.info(f"最终音频文件: {audio_file}")
            return audio_file, video_title

        except Exception as e:
            logger.error(f"视频处理失败: {str(e)}")
            raise Exception(f"视频处理失败: {str(e)}")
        # 【修复1】函数内内容缩进结束（到这里为止）
    
    def get_video_info(self, url: str) -> dict:
        """
        获取视频信息
        
        Args:
            url: 视频链接
            
        Returns:
            视频信息字典
        """
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', ''),
                    'upload_date': info.get('upload_date', ''),
                    'description': info.get('description', ''),
                    'view_count': info.get('view_count', 0),
                }
        except Exception as e:
            logger.error(f"获取视频信息失败: {str(e)}")
            raise Exception(f"获取视频信息失败: {str(e)}")