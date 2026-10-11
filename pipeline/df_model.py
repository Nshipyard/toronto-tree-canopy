#!/usr/bin/env python3
"""df_model.py — load DeepForest with locally-downloaded release weights.

The sandbox egress proxy breaks huggingface_hub/httpx proxy parsing, so the
weights (weecology/deepforest-tree, MIT) were fetched with curl to
data/weights/model.safetensors and are loaded here without any network.

Two torchvision quirks are patched in-process (no system changes):
1. WeightsEnum.verify(None) returns DEFAULT in this torchvision version, which
   would trigger a backbone download; patched so None means random-init.
2. retinanet_resnet50_fpn defaults weights_backbone to IMAGENET1K_V1; the
   backbone builder looked up inside detection.retinanet is wrapped to force
   weights=None.

Every parameter is then overwritten from the local safetensors file, so the
random init is irrelevant.
"""
import os

# Strip proxy env vars: huggingface_hub/httpx chokes parsing them (notably
# NO_PROXY's [::1]); inference needs no network at all.
for _k in list(os.environ):
    if "proxy" in _k.lower():
        del os.environ[_k]

import torchvision.models.detection.retinanet as _dr
import torchvision.models.resnet as _resnet

# 1. verify(None) -> None instead of DEFAULT
for _cls in (_dr.RetinaNet_ResNet50_FPN_Weights, _resnet.ResNet50_Weights):
    _orig = _cls.verify.__func__
    _cls.verify = classmethod(lambda cls, w, _o=_orig: None if w is None else _o(cls, w))

# 2. force weights=None on the backbone builder used by retinanet_resnet50_fpn
_orig_rn_resnet50 = _dr.resnet50


def _resnet50_no_download(*, weights=None, **kwargs):
    return _orig_rn_resnet50(weights=None, **kwargs)


_dr.resnet50 = _resnet50_no_download

from deepforest import main as df_main
from deepforest.models.retinanet import RetinaNetHub
from safetensors.torch import load_file

WEIGHTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "weights", "model.safetensors")


def load_model(weights_path=WEIGHTS, score_thresh=0.15, nms_thresh=0.15):
    """Build RetinaNet (random init, no downloads) and load local weights."""
    base = RetinaNetHub(backbone_weights=None,
                       num_classes=1,
                       nms_thresh=nms_thresh,
                       score_thresh=score_thresh,
                       label_dict={"Tree": 0})
    sd = None
    if weights_path.endswith(".safetensors"):
        sd = load_file(weights_path)
    else:
        import torch
        sd = torch.load(weights_path, map_location="cpu", weights_only=True)
    missing, unexpected = base.load_state_dict(sd, strict=False)
    print(f"  state dict: {len(sd)} tensors, missing={len(missing)}, "
          f"unexpected={len(unexpected)}", flush=True)
    if missing:
        print("  WARNING missing keys (head):", list(missing)[:5], flush=True)
    m = df_main.deepforest(model=base)
    m.config.num_classes = 1
    m.set_labels(base.label_dict)
    m.model.score_thresh = score_thresh
    return m
