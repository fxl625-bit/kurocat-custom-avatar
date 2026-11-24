import base64
from io import BytesIO
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import argparse

def encode(im):
    out=BytesIO()
    im.save(out,'WEBP',quality=88,method=4)
    return 'data:image/webp;base64,'+base64.b64encode(out.getvalue()).decode()
def layer(im,mask):
    box=Image.fromarray(mask).getbbox()
    tile=Image.fromarray(im).convert('RGBA')
    tile.putalpha(Image.fromarray(mask))
    return dict(x=box[0],y=box[1],src=encode(tile.crop(box)))
def make_eye(rgb,X,Y,e):
    cx,cy,rx,ry,x0,y0,x1,y1=e
    pts=[(x0,cy),(x0+2,y0+2),(cx,y0),(x1-2,y0+1),(x1,cy),(x1-2,y1-2),(cx,y1),(x0+2,y1-1)]
    aperture=np.zeros(rgb.shape[:2],np.uint8)
    cv2.fillPoly(aperture,[np.rint(pts).astype(np.int32)],255,lineType=cv2.LINE_AA)
    dist=((X-cx)/rx)**2+((Y-cy)/ry)**2
    iris=np.minimum(np.clip((1.15-dist)*450,0,255).astype(np.uint8),aperture)
    fill=cv2.inpaint(rgb,cv2.dilate(iris,np.ones((3,3),np.uint8)),3,cv2.INPAINT_TELEA)
    cover=cv2.dilate(aperture,np.ones((4,4),np.uint8))
    lid=cv2.inpaint(rgb,cover,5,cv2.INPAINT_TELEA)
    cv2.polylines(lid,[np.rint([(x0,cy),(cx,cy+2),(x1,cy)]).astype(np.int32)],False,(57,39,34),1,cv2.LINE_AA)
    return dict(cx=cx,cy=cy,outline=pts,fill=layer(fill,aperture),iris=layer(rgb,iris),blink=layer(lid,cover))
def make(art_path, cfg, output):
    art=Image.open(art_path).convert('RGBA')
    # Give isolated hands transparent room to move at the left or right edge.
    margin=20
    width=art.width+2*margin
    height=cfg['waist']+24
    rgba=Image.new('RGBA',(width,height));rgba.paste(art.crop((0,0,art.width,height)),(margin,0))
    src=np.float32(rgba)/255
    src[:,:,:3]*=src[:,:,3,None]
    Y,X=np.mgrid[:height,:width].astype(np.float32)
    def displacement(handles):
        dx=np.zeros_like(X);dy=np.zeros_like(Y)
        for x,y,rx,ry,tx,ty in handles:
            dist=((X-x-margin)/rx)**2+((Y-y)/ry)**2
            f=np.clip(1-dist/2.2,0,1)**2
            dx+=tx*f;dy+=ty*f
        return dx,dy
    lx,ly=displacement(cfg['left']);rx,ry=displacement(cfg['right'])
    states=5
    atlas=Image.new('RGBA',(width*states,height*states))
    for i in range(states):
        for j in range(states):
            a=i/(states-1);b=j/(states-1)
            moved=cv2.remap(src,X-a*lx-b*rx,Y-a*ly-b*ry,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            moved[:,:,:3]/=np.maximum(moved[:,:,3,None],1e-5)
            # Rotated subrectangles in Canvas sample neighbouring atlas texels.
            # Leave a transparent gutter below the waist and in the side margins.
            moved[-5:,:,:]=0
            moved[:,:4,:]=0
            moved[:,-4:,:]=0
            atlas.paste(Image.fromarray(np.clip(moved*255+.5,0,255).astype(np.uint8)),(i*width,j*height))
    eyes=[]
    for cx,cy,r1,r2,x0,y0,x1,y1 in cfg['eyes']:
        eyes.append(make_eye(np.array(rgba.convert('RGB')),X,Y,(cx+margin,cy,r1,r2,x0+margin,y0,x1+margin,y1)))
    x,y=cfg['neck']
    data=dict(kind='anime',label=cfg['label'],atlas=encode(atlas),states=states,width=width,height=height,
              neck=[x+margin,y],faceEnd=cfg['faceEnd'],collar=cfg['collar'],waist=cfg['waist'],eyes=eyes)
    payload=json.dumps(data,separators=(',',':'),ensure_ascii=False).encode()
    if len(payload)>2_000_000:
        raise ValueError("Atlas exceeds 2 MB. Resize the input and its coordinates.")
    output.write_bytes(payload)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description="Prepare a layered avatar atlas from your own transparent upper-body illustration.")
    parser.add_argument('image',type=Path)
    parser.add_argument('landmarks',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    make(args.image,json.loads(args.landmarks.read_text(encoding='utf8')),args.output)
