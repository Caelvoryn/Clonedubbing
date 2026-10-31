"""Standalone five-style local narration application."""
import os
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'

from contextlib import ExitStack
import gc
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import gradio as gr
import numpy as np
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parent
PROFILE_FILE = Path(os.environ.get('VOICE_PROFILES', str(ROOT / 'voices/profiles.json')))
PROFILES = json.loads(PROFILE_FILE.read_text(encoding='utf-8'))
if not PROFILES:
    raise RuntimeError('请先配置 voices/profiles.json 和服务器参考音频。')
MODEL_PATH = Path(os.environ.get('VOICE_MODEL', str(ROOT / 'models/Qwen3-TTS-12Hz-1.7B-Base')))
_model = None
_prompts = {}
_lock = threading.Lock()
_progress = gr.Progress()

def device_description():
    if os.environ.get('VOICE_DEVICE') == 'cpu':
        return 'CPU兼容模式（手动指定，生成较慢）'
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        return f'GPU加速：{props.name}，显存{props.total_memory/1024**3:.1f}GB'
    return 'CPU兼容模式：未检测到可用CUDA。请先更新英伟达显卡驱动，重启本程序。'

def load_model_original():
    global _model
    if _model is None:
        from qwen_tts import Qwen3TTSModel
        torch.set_num_threads(min(6, os.cpu_count() or 1))
        gpu = torch.cuda.is_available() and os.environ.get('VOICE_DEVICE') != 'cpu'
        model = Qwen3TTSModel.from_pretrained(str(MODEL_PATH), device_map='cpu',
            dtype=(torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16) if gpu else torch.float32,
            attn_implementation='sdpa', low_cpu_mem_usage=True, local_files_only=True)
        codec = model.model.speech_tokenizer
        codec.model.to(device='cpu', dtype=torch.float32)
        codec.device = torch.device('cpu')
        if gpu:
            model.model.to('cuda:0')
            model.device = torch.device('cuda:0')
        _model = model
    return _model


_active_path = None
def load_model(voice=None):
    global _active_path, _model
    profile = PROFILES.get(voice, {})
    target = Path(profile.get('model_path', MODEL_PATH))
    if _model is not None and _active_path != target:
        _model = None
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()
    if _model is None:
        from qwen_tts import Qwen3TTSModel
        gpu = torch.cuda.is_available() and os.environ.get('VOICE_DEVICE') != 'cpu'
        torch.set_num_threads(min(6, os.cpu_count() or 1))
        model = Qwen3TTSModel.from_pretrained(str(target),device_map='cpu',dtype=(torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16) if gpu else torch.float32,attn_implementation='sdpa',low_cpu_mem_usage=True,local_files_only=True)
        model.model.speech_tokenizer.model.to(device='cpu',dtype=torch.float32)
        model.model.speech_tokenizer.device=torch.device('cpu')
        if gpu: model.model.to('cuda:0'); model.device=torch.device('cuda:0')
        _model=model
        _active_path=target
    return _model

def chunks(text):
    units = re.split(r'(?<=[。！？!?；;])\s*|\n+', text.strip())
    result, current = [], ''
    for unit in units:
        if not unit.strip():
            continue
        if len(current) + len(unit) > 160 and current:
            result.append(current)
            current = ''
        while len(unit) > 160:
            cut = unit.rfind('，', 50, 160)
            if cut < 0:
                cut = unit.rfind(' ', 50, 160)
            cut = cut + 1 if cut >= 0 else 160
            if current:
                result.append(current)
                current = ''
            result.append(unit[:cut])
            unit = unit[cut:]
        current += unit
    if current:
        result.append(current)
    return result

def reference(voice):
    profile = PROFILES[voice]
    return str(ROOT / profile['reference']), profile['transcript']

def select_voice(voice):
    path, transcript = reference(voice)
    language = '英文' if PROFILES[voice].get('language') == 'English' else '中文'
    return path, transcript, gr.update(value=language)

def generate(voice, text, mode, language, gap, progress=_progress):
    if voice not in PROFILES:
        raise gr.Error('请选择声线。')
    text = (text or '').strip()
    if not text:
        raise gr.Error('请输入文案。')
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if mode == '五声线依次接读' and len(paragraphs) == 1:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
        if len(paragraphs) < 2:
            raise gr.Error('接读时请将文案分段，每段之间空一行，依次使用声线01—05。')
    tasks = []
    voices = [key for key in PROFILES if key.startswith('声线')]
    for index, paragraph in enumerate(paragraphs):
        selected = voices[index % len(voices)] if mode == '五声线依次接读' else voice
        for number, segment in enumerate(chunks(paragraph)):
            tasks.append((selected, segment, float(gap) if index > 0 and number == 0 else (.12 if number else 0)))
    with _lock, ExitStack() as stack:
        output_dir = ROOT / 'outputs'
        output_dir.mkdir(exist_ok=True)
        stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
        output = output_dir / f'配音_{stamp}_{uuid4().hex[:6]}.wav'
        writer = stack.enter_context(sf.SoundFile(output, mode='w', samplerate=24000, channels=1, subtype='PCM_16', format='WAV'))
        total_samples = 0
        progress(.02, desc='正在加载本地1.7B模型，首次加载稍慢…')
        model = load_model(voice)
        parts, records = [], []
        for index, (selected, segment, pause) in enumerate(tasks):
            progress(.06+.9*index/len(tasks), desc=f'正在生成第{index+1}/{len(tasks)}段，{selected}')
            model = load_model(selected)
            trained = PROFILES[selected].get('mode') == 'finetuned'
            if not trained and selected not in _prompts:
                path, transcript = reference(selected)
                audio, rate = sf.read(path, dtype='float32')
                x_vector_only = PROFILES[selected].get('x_vector_only', False)
                _prompts[selected] = model.create_voice_clone_prompt(ref_audio=(audio, rate),
                    ref_text=None if x_vector_only else transcript, x_vector_only_mode=x_vector_only)
            synthesis = segment.replace('将进酒', '羌进酒').replace('50-18','五零幺八').replace('5018','五零幺八').replace('35-07','三五零七')
            try:
                with torch.inference_mode():
                    if trained:
                        wavs, sr = model.generate_custom_voice(text=synthesis, language={'自动':'Auto','中文':'Chinese','英文':'English'}[language], speaker=PROFILES[selected]['speaker_id'], non_streaming_mode=True, temperature=.75, max_new_tokens=1400)
                    else:
                        wavs, sr = model.generate_voice_clone(text=synthesis,
                            language={'自动': 'Auto', '中文': 'Chinese', '英文': 'English'}[language],
                            voice_clone_prompt=_prompts[selected], non_streaming_mode=True,
                            temperature=.75, max_new_tokens=1400)
            except torch.cuda.OutOfMemoryError as exc:
                gc.collect()
                torch.cuda.empty_cache()
                raise gr.Error('显存不足，请关闭占用显卡的游戏或视频软件，并缩短文案段落后重试。') from exc
            audio = np.asarray(wavs[0], dtype='float32')
            if not np.isfinite(audio).all() or not .2 < len(audio)/sr < 115 or np.max(np.abs(audio)) < .001:
                raise gr.Error('本段生成异常，请重试。')
            peak = float(np.max(np.abs(audio)))
            if peak > .98:
                audio *= .98/peak
            fade = min(round(sr*.008), len(audio)//2)
            audio[:fade] *= np.linspace(0, 1, fade, dtype='float32')
            audio[-fade:] *= np.linspace(1, 0, fade, dtype='float32')
            if records and pause:
                silence = np.zeros(round(sr*pause), dtype='float32')
                writer.write(silence)
                total_samples += len(silence)
            writer.write(audio)
            writer.flush()
            total_samples += len(audio)
            records.append({'voice': selected, 'text': segment, 'synthesis_text': synthesis,
                'pause_before': pause, 'duration': len(audio)/sr})
        writer.close()
        metadata = {'mode': mode, 'text': text, 'segments': records, 'duration': total_samples/sr,
            'device': str(model.device), 'model': str(MODEL_PATH), 'audio_uploaded': False,
            'tempo_adjustment': False}
        output.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        progress(1, desc='完成')
        return str(output), str(output), f'已生成{total_samples/sr:.1f}秒，使用{model.device}。音色和语气请试听判断。'

def shutdown():
    threading.Timer(1, lambda: os._exit(0)).start()
    return '程序已关闭，可以关闭此页面。'

def build_ui():
    first = next(iter(PROFILES))
    choices = [(f"{key} · {p['label']}", key) for key, p in PROFILES.items()]
    with gr.Blocks(title='综合声线配音') as ui:
        gr.Markdown('# 配音工作台\n所有已整理声线统一选择，长文自动分段，无固定总字数上限。选择声音后填写文案，文案在配音服务器处理，生成后可试听、下载。')
        gr.Textbox(value=device_description(), label='运行状态', interactive=False)
        voice = gr.Dropdown(choices=choices, value=first, label='选择声线')
        original = gr.Audio(value=reference(first)[0], label='这一声线的原声参考', interactive=False)
        words = gr.Textbox(value=reference(first)[1], label='原声内容', interactive=False)
        mode = gr.Radio(['选定声线朗读', '五声线依次接读'], value='选定声线朗读', label='朗读方式')
        gr.Markdown('五声线接读：每段之间空一行，依次使用01—05，超过五段后循环。')
        text = gr.Textbox(value='夜色渐深，远处的灯光依然亮着，一个新的故事，即将开始。', label='配音文案', lines=8)
        language = gr.Dropdown(['自动', '中文', '英文'], value='中文', label='语言')
        voice.change(select_voice, voice, [original, words, language])
        gap = gr.Slider(0, 2, value=.7, step=.1, label='段间停顿（秒）')
        button = gr.Button('生成配音', variant='primary')
        audio = gr.Audio(label='生成试听', type='filepath')
        download = gr.File(label='下载WAV音频')
        status = gr.Textbox(label='生成状态', interactive=False)
        button.click(generate, [voice, text, mode, language, gap], [audio, download, status], concurrency_limit=1)

    return ui

if __name__ == '__main__':
    if os.environ.get('VOICE_HOST', '127.0.0.1') not in ('127.0.0.1', 'localhost') and not (os.environ.get('VOICE_USER') and os.environ.get('VOICE_PASSWORD')):
        raise RuntimeError('对外服务必须设置 VOICE_USER 和 VOICE_PASSWORD。')
    build_ui().queue(max_size=8).launch(server_name=os.environ.get('VOICE_HOST','127.0.0.1'), server_port=int(os.environ.get('VOICE_PORT','7865')), share=False, inbrowser=False, auth=((os.environ['VOICE_USER'],os.environ['VOICE_PASSWORD']) if os.environ.get('VOICE_USER') and os.environ.get('VOICE_PASSWORD') else None))
