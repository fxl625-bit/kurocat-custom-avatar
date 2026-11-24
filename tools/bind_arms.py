"""Bind two independently posed arms to a transparent character illustration."""
import argparse
import base64
import json
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def layer(rgb, alpha):
    y, x = np.nonzero(alpha)
    x0, y0, x1, y1 = int(x.min()), int(y.min()), int(x.max()+1), int(y.max()+1)
    image = Image.fromarray(np.dstack((rgb, alpha))).crop((x0, y0, x1, y1))
    result = BytesIO()
    image.save(result, 'WEBP', quality=94)
    return dict(x=x0, y=y0, src='data:image/webp;base64,' + base64.b64encode(result.getvalue()).decode())


def rounded_segment(rgb, alpha, joints, radii, margin):
    # Fill a tapered, rounded joint from the nearest real pixels of its sleeve.
    # This preserves the character artwork when its foreshortened arm extends.
    from scipy.ndimage import distance_transform_edt
    a,b=np.array(joints,np.float32)+[margin,0]
    axis=b-a
    length=np.linalg.norm(axis)
    yy,xx=np.mgrid[:alpha.shape[0],:alpha.shape[1]]
    t=((xx-a[0])*axis[0]+(yy-a[1])*axis[1])/length
    v=np.abs((xx-a[0])*axis[1]-(yy-a[1])*axis[0])/length
    radius=np.interp(t,[0,length],radii)
    over=np.maximum(np.maximum(-t,t-length),0)
    edge=radius*(1-np.sqrt((v/radius)**2+(over/(radius*.54))**2))
    shape=np.clip((edge+.5)*255,0,255).astype(np.uint8)
    source=(alpha>105)&(shape>64)
    if not source.any():raise ValueError("No usable sleeve pixels")
    iy,ix=distance_transform_edt(~source,return_distances=False,return_indices=True)
    return np.dstack((rgb[iy,ix],shape))


def bind(art_path, atlas_path, binding_path, output):
    rig = json.loads(atlas_path.read_text(encoding='utf8'))
    spec = json.loads(binding_path.read_text(encoding='utf8'))
    w, h = rig['width'], rig['height']
    art = Image.open(art_path).convert('RGBA')
    margin = (w-art.width)//2
    frame = Image.new('RGBA',(w,h))
    frame.paste(art.crop((0,0,art.width,h)),(margin,0))
    pixels = np.array(frame)
    rgb, alpha = pixels[:,:,:3].copy(), pixels[:,:,3].copy()
    removed = np.zeros_like(alpha)
    arms = []
    extracted = []
    for arm in spec['arms']:
        parts = []
        for index, poly in enumerate(arm['p']):
            mask = np.zeros_like(alpha)
            vertices = np.asarray(poly,np.int32) + [margin,0]
            cv2.fillPoly(mask,[vertices.astype(np.int32)],255,lineType=cv2.LINE_AA)
            # Only a small overlap at a joint is needed. Material extending past
            # a foreshortened segment would grow into a spike as the arm reaches.
            clipped = np.minimum(alpha,mask)
            if index < 2:
                start, end = np.array(arm['j'][index:index+2],np.float32) + [margin,0]
                axis = end-start
                length = np.linalg.norm(axis)
                yy,xx=np.mgrid[:h,:w]
                along=((xx-start[0])*axis[0]+(yy-start[1])*axis[1])/length
                across=np.abs((xx-start[0])*axis[1]-(yy-start[1])*axis[0])/length
                radius = (14 if index==0 else 10)
                outside=np.maximum(np.maximum(-along,along-length),0)
                cap=np.clip(1-(outside / 5)**2-(across / radius)**2,0,1)
                clipped=np.where(outside>0,clipped*cap,clipped).astype(np.uint8)
            if index < 2 and 'radii' in arm:
                piece=rounded_segment(rgb,clipped,arm['j'][index:index+2],arm['radii'][index],margin)
                parts.append(layer(piece[:,:,:3],piece[:,:,3]))
            else:
                piece=np.dstack((rgb,clipped))
                parts.append(layer(rgb,clipped))
            if index==0:
                extracted.append(piece)
            removed = np.maximum(removed,mask)
        arms.append(dict(joints=[dict(x=x+margin,y=y) for x,y in arm['j']],parts=parts))
    removed = cv2.dilate(removed,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
    for i,arm in enumerate(spec['arms']):
        if 'upperDonor' not in arm:
            continue
        donor=arm['upperDonor']
        def basis(joints, mirror):
            a,b=np.float32(joints[:2])+[margin,0]
            d=(b-a)/np.linalg.norm(b-a)
            return np.float32([a,b,a+np.array([-d[1],d[0]])*15*mirror])
        affine=cv2.getAffineTransform(basis(spec['arms'][donor]['j'],1),basis(arm['j'],-1))
        warped=cv2.warpAffine(extracted[donor],affine,(w,h))
        if 'radii' in arm:
            warped=rounded_segment(warped[:,:,:3],warped[:,:,3],arm['j'][:2],arm['radii'][0],margin)
        arms[i]['parts'][0]=layer(warped[:,:,:3],warped[:,:,3])
    for poly in spec.get('keep',[]):
        coords=np.asarray(poly,np.int32)+[margin,0]
        cv2.fillPoly(removed,[coords.astype(np.int32)],0)
    clean = cv2.inpaint(rgb,removed,7,cv2.INPAINT_TELEA)
    ys,left,right = np.array(spec['edge']).T
    y,x = np.mgrid[:h,:w]
    inside = (x>=margin+np.interp(y,ys,left)) & (x<=margin+np.interp(y,ys,right))
    # Drop the entirety of each original outer arm contour, including baked
    # drop shadows. Feather the reconstructed silhouette by one source pixel.
    near_arm=cv2.dilate(removed,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(61,61)))>0
    boundary=np.where((y>=ys[0]) & (y<=ys[-1]) & near_arm,inside,True).astype(np.uint8)*255
    boundary=cv2.GaussianBlur(boundary,(3,3),.55)
    cleaned_alpha=np.minimum(boundary,alpha)
    rig['articulation'] = dict(torso=layer(clean,cleaned_alpha),arms=arms)
    payload = json.dumps(rig,separators=(',',':'),ensure_ascii=False).encode()
    if len(payload)>2_000_000:
        raise ValueError('Rig exceeds the desktop reader limit of 2 MB')
    output.write_bytes(payload)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('art','atlas','binding','output'):
        parser.add_argument(name,type=Path)
    args=parser.parse_args()
    bind(args.art,args.atlas,args.binding,args.output)
