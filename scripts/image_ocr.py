"""Local image text recognition and a derived package; original extraction stays intact."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def recognize(image):
    script = Path(__file__).with_name('ocr-image.swift')
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    directory = Path.home()/'.cache/personal-wiki/vision'/digest
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    binary = directory/'recognize'
    if not binary.exists():
        temporary = directory/f'recognize-{os.getpid()}'
        subprocess.run(['/usr/bin/swiftc', str(script), '-o', str(temporary)], check=True, capture_output=True, timeout=120)
        os.replace(temporary, binary)
    result = subprocess.run([str(binary), str(image)], check=True, capture_output=True, timeout=120, text=True)
    return json.loads(result.stdout)


def convert_package(source, output):
    source, output = Path(source).resolve(), Path(output).absolute()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('OCR output must be separate from the extracted package')
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Package symlink rejected')
    original = (source/'article.md').read_text()
    images = {p.relative_to(source).as_posix(): p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.gif','.tiff','.bmp')}
    if not images:return dict(directory=str(source), ocrImages=0)
    # First follow Markdown order; supplementary covers follow afterward.
    linked = re.findall(r'!\[[^\]]*\]\(([^\s)]+)', original)
    order = list(dict.fromkeys([p for p in linked if p in images] + sorted(images)))
    results, sections = [], []
    for relative in order:
        result = recognize(images[relative])
        if result.get('frame_count') != result.get('processed_frames'):
            raise ValueError('Image frames incomplete; original retained')
        result.update(image=relative, sha256=hashlib.sha256(images[relative].read_bytes()).hexdigest())
        results.append(result)
        lines = [line['text'] + (f"〔首次出现于帧 {line['first_frame']+1}〕" if result['frame_count']>1 else '') + ('〔识别不确定〕' if line['confidence'] < 0.5 else '') for line in result['lines']]
        sections.append('### '+relative+'\n\n[原图]('+relative+')\n\n'+('\n\n'.join(lines) or '未检测到可识别文字。'))
    reading = '# 图片文字识别\n\n> 本机 Apple Vision 机器识别，未经人工校订。原图为准；多栏顺序和识别准确性可能有误。\n\n'+'\n\n'.join(sections)+'\n'
    if output.exists():
        if (output/'article.extracted.md').read_text()!=original:
            raise ValueError('Existing OCR extraction differs; preserve version')
        return dict(directory=str(output), ocrImages=len(images))
    stage=output.with_name(output.name+f'.stage-{os.getpid()}')
    try:
        shutil.copytree(source, stage)
        (stage/'article.extracted.md').write_text(original)
        (stage/'image-text.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
        (stage/'image-text.md').write_text(reading)
        (stage/'article.md').write_text(original+'\n\n## 图片文字（独立机器识别）\n\n'+reading.replace('# 图片文字识别\n','',1))
        os.rename(stage, output)
    finally:
        if stage.exists():shutil.rmtree(stage)
    return dict(directory=str(output), ocrImages=len(images))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--package')
    parser.add_argument('--output')
    parser.add_argument('--image')
    args=parser.parse_args()
    print(json.dumps(recognize(args.image) if args.image else convert_package(args.package, args.output), ensure_ascii=False))
