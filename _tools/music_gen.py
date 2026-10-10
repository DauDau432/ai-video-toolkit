"""Sinh nhạc nền không lời bằng ACE-Step 1.5. Chạy trong môi trường riêng _models/ace-step
(ACE-Step cần Python 3.11-3.12), do `videokit.py music` gọi; không chạy trực tiếp."""
import argparse
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

ACE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_models", "ace-step"))

ap = argparse.ArgumentParser()
ap.add_argument("--caption", required=True)
ap.add_argument("--seconds", type=float, required=True)
ap.add_argument("--bpm", type=int)
ap.add_argument("--seed", type=int)
ap.add_argument("--out", required=True)
args = ap.parse_args()

import torch
from acestep.gpu_config import get_gpu_config, get_gpu_memory_gb
from acestep.handler import AceStepHandler
from acestep.inference import GenerationConfig, GenerationParams, generate_music
from acestep.llm_inference import LLMHandler

device = "cuda" if torch.cuda.is_available() else "cpu"
gpu = get_gpu_config(get_gpu_memory_gb()) if device == "cuda" else None
offload = gpu.offload_to_cpu_default if gpu else False

dit = AceStepHandler()
msg, ok = dit.initialize_service(project_root=ACE, config_path="acestep-v15-turbo", device=device,
                                 offload_to_cpu=offload, offload_dit_to_cpu=gpu.offload_dit_to_cpu_default if gpu else False)
if not ok:
    sys.exit(f"Không nạp được model nhạc: {msg}")

# Mô hình ngôn ngữ của ACE-Step lên bố cục bài nhạc; dùng bản lớn nhất card chịu được (bỏ qua nếu card quá yếu)
llm = LLMHandler()
lm = gpu.available_lm_models[-1] if gpu and gpu.available_lm_models else None
if lm:
    from acestep.model_downloader import ensure_lm_model
    ensure_lm_model(lm, checkpoints_dir=Path(ACE, "checkpoints"))
    msg, ok = llm.initialize(checkpoint_dir=os.path.join(ACE, "checkpoints"), lm_model_path=lm,
                             backend="pt", device=device, offload_to_cpu=offload)
    if not ok:
        print(f"Bỏ qua mô hình ngôn ngữ ({msg}), chỉ dùng DiT.")

params = GenerationParams(caption=args.caption, lyrics="[Instrumental]", instrumental=True,
                          duration=args.seconds, bpm=args.bpm, thinking=llm.llm_initialized,
                          use_cot_caption=False, use_cot_language=False)  # giữ nguyên mô tả của agent, không để LM viết lại
# ACE-Step không đặt seed cho mô hình ngôn ngữ khi sinh 1 bản, nên tự đặt seed chung để --seed sinh lại đúng bản cũ
seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
torch.manual_seed(seed)
config = GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=False, seeds=[seed])
with tempfile.TemporaryDirectory() as tmp:
    result = generate_music(dit, llm, params, config, save_dir=tmp)
    if not result.success or not result.audios:
        sys.exit(f"Sinh nhạc thất bại: {result.error}")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    shutil.copyfile(result.audios[0]["path"], args.out)
print(f"seed={seed}")
