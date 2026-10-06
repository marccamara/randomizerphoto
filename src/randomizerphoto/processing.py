import os
import random
import json
import datetime
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import piexif

IPHONE_MODELS = [
    {"make": "Apple", "model": "iPhone 11", "software": "16.5", "focal": (26, 1), "fnum": (18, 10)},
    {"make": "Apple", "model": "iPhone 12", "software": "17.1.1", "focal": (26, 1), "fnum": (16, 10)},
    {"make": "Apple", "model": "iPhone 13", "software": "17.4", "focal": (26, 1), "fnum": (16, 10)},
    {"make": "Apple", "model": "iPhone 14", "software": "17.5.1", "focal": (26, 1), "fnum": (15, 10)},
    {"make": "Apple", "model": "iPhone 15", "software": "17.6", "focal": (24, 1), "fnum": (16, 10)},
]


def load_history(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_history(history_set, path):
    with open(path, "w") as f:
        json.dump(list(history_set), f)


def generate_unique_filename(used):
    while True:
        r = random.randint(1000, 9999)
        if r not in used:
            used.add(r)
            return f"IMG_{r}.jpg"


def generate_iphone_exif(model_name=None):
    pool = IPHONE_MODELS
    if model_name and model_name != "Mix":
        pool = [m for m in IPHONE_MODELS if m["model"] == model_name] or IPHONE_MODELS
    device = random.choice(pool)

    now = datetime.datetime.now()
    d = now - datetime.timedelta(days=random.randint(1, 30), seconds=random.randint(0, 86400))
    date_str = d.strftime("%Y:%m:%d %H:%M:%S")

    zeroth = {
        piexif.ImageIFD.Make: device["make"],
        piexif.ImageIFD.Model: device["model"],
        piexif.ImageIFD.Software: f"iOS {device['software']}",
        piexif.ImageIFD.Orientation: 1,
        piexif.ImageIFD.XResolution: (72, 1),
        piexif.ImageIFD.YResolution: (72, 1),
        piexif.ImageIFD.ResolutionUnit: 2,
        piexif.ImageIFD.DateTime: date_str,
    }
    exif = {
        piexif.ExifIFD.DateTimeOriginal: date_str,
        piexif.ExifIFD.DateTimeDigitized: date_str,
        piexif.ExifIFD.OffsetTimeOriginal: "+03:00",
        piexif.ExifIFD.ColorSpace: 1,
        piexif.ExifIFD.ExifVersion: b"0232",
        piexif.ExifIFD.ComponentsConfiguration: b"\x01\x02\x03\x00",
        piexif.ExifIFD.FocalLength: device["focal"],
        piexif.ExifIFD.FNumber: device["fnum"],
        piexif.ExifIFD.ISOSpeedRatings: random.choice([50, 64, 80, 100, 125, 160]),
        piexif.ExifIFD.LensModel: f"{device['model']} back camera 5.96mm f/{device['fnum'][0]/10}",
    }
    return piexif.dump({"0th": zeroth, "Exif": exif, "1st": {}, "GPS": {}, "Interop": {}})


def add_gaussian_noise_and_steganography(img, magnitude=2.5):
    arr = np.array(img).astype(np.int16)
    arr = arr + np.random.normal(0, magnitude, arr.shape)
    shifts = np.random.choice([-1, 0, 1], size=arr.shape, p=[0.1, 0.8, 0.1])
    arr = arr + shifts
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def dynamic_crop_to_ratio(img, target_ratio=(3, 4)):
    w, h = img.size
    ta = target_ratio[0] / target_ratio[1]
    if w / h > ta:
        nw, nh = int(h * ta), h
        mo = w - nw
        left, top = (random.randint(0, mo) if mo > 0 else 0), 0
    else:
        nw, nh = w, int(w / ta)
        mo = h - nh
        left, top = 0, (random.randint(0, mo) if mo > 0 else 0)
    return img.crop((left, top, left + nw, top + nh))


def process_single_image(img, output_path, target_width=1080, model=None):
    if random.random() < 0.15:
        img = ImageOps.mirror(img)
    img = dynamic_crop_to_ratio(img, (3, 4))
    img = img.resize((target_width, int(target_width * 4 / 3)), Image.Resampling.LANCZOS)
    img = img.copy()
    img = img.rotate(random.uniform(-0.5, 0.5), resample=Image.BICUBIC, expand=False)
    img = ImageEnhance.Brightness(img).enhance(random.uniform(0.97, 1.03))
    img = ImageEnhance.Contrast(img).enhance(random.uniform(0.97, 1.03))
    img = ImageEnhance.Color(img).enhance(random.uniform(0.98, 1.02))
    img = add_gaussian_noise_and_steganography(img, random.uniform(1.8, 3.2))
    img.save(output_path, format="JPEG", quality=random.randint(92, 96),
             optimize=True, exif=generate_iphone_exif(model))


def process_folder_advanced(input_folder, output_base_folder, num_folders=10,
                            history_path="used_file_names.json", progress=None, model=None):
    exts = ('.jpg', '.jpeg', '.png', '.webp')
    files = [f for f in os.listdir(input_folder) if f.lower().endswith(exts)]
    if not files:
        return
    used = load_history(history_path)
    total = num_folders * len(files)
    done = 0
    for i in range(1, num_folders + 1):
        sub = os.path.join(output_base_folder, f"dossier_{i}")
        os.makedirs(sub, exist_ok=True)
        for name in files:
            out = os.path.join(sub, generate_unique_filename(used))
            try:
                with Image.open(os.path.join(input_folder, name)) as img:
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img = ImageOps.exif_transpose(img)
                    process_single_image(img, out, model=model)
            except Exception as e:
                print(f"[-] Erreur sur {name} : {e}")
            done += 1
            if progress:
                progress(done, total)
    save_history(used, history_path)
