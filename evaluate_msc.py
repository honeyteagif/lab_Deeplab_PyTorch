import torch
import argparse
import scipy
from scipy import ndimage
import numpy as np
import sys
from torch.autograd import Variable
import torchvision.models as models
import torch.nn.functional as F
from torch.utils import data
from deeplab.model import Res_Deeplab
from deeplab.datasets import VOCDataSet
from collections import OrderedDict
import os

import cv2
import matplotlib.pyplot as plt
import torch.nn as nn
IMG_MEAN = np.array((104.00698793,116.66876762,122.67891434), dtype=np.float32)

DATA_DIRECTORY = '/home/wty/AllDataSet/VOC2012/'
DATA_LIST_PATH = './dataset/list/val.txt'
IGNORE_LABEL = 255
NUM_CLASSES = 21
NUM_STEPS = 1449 # Number of images in the validation set.
RESTORE_FROM = './snapshots_bs10/VOC12_scenes_20000.pth'
#RESTORE_FROM = './pretrained/VOC12_scenes_20000.pth'

def get_arguments():
    """Parse all the arguments provided from the CLI.
    
    Returns:
      A list of parsed arguments.
    """
    parser = argparse.ArgumentParser(description="DeepLabLFOV Network")
    parser.add_argument("--data-dir", type=str, default=DATA_DIRECTORY,
                        help="Path to the directory containing the PASCAL VOC dataset.")
    parser.add_argument("--data-list", type=str, default=DATA_LIST_PATH,
                        help="Path to the file listing the images in the dataset.")
    parser.add_argument("--ignore-label", type=int, default=IGNORE_LABEL,
                        help="The index of the label to ignore during the training.")
    parser.add_argument("--num-classes", type=int, default=NUM_CLASSES,
                        help="Number of classes to predict (including background).")
    parser.add_argument("--restore-from", type=str, default=RESTORE_FROM,
                        help="Where restore model parameters from.")
    parser.add_argument("--gpu", type=int, default=2,
                        help="choose gpu device.")
    return parser.parse_args()


def get_iou(data_list, class_num, save_path=None):
    from multiprocessing import Pool 
    from deeplab.metric import ConfusionMatrix

    ConfM = ConfusionMatrix(class_num)
    f = ConfM.generateM
    pool = Pool() 
    m_list = pool.map(f, data_list)
    pool.close() 
    pool.join() 
    
    for m in m_list:
        ConfM.addM(m)

    aveJ, j_list, M = ConfM.jaccard()
    print('meanIOU: ' + str(aveJ) + '\n')
    if save_path:
        with open(save_path, 'w') as f:
            f.write('meanIOU: ' + str(aveJ) + '\n')
            f.write(str(j_list)+'\n')
            f.write(str(M)+'\n')

def show_all(gt, pred):
    import matplotlib.pyplot as plt
    from matplotlib import colors
    from mpl_toolkits.axes_grid1 import make_axes_locatable

    fig, axes = plt.subplots(1, 2)
    ax1, ax2 = axes

    classes = np.array(('background',  # always index 0
               'aeroplane', 'bicycle', 'bird', 'boat',
               'bottle', 'bus', 'car', 'cat', 'chair',
                         'cow', 'diningtable', 'dog', 'horse',
                         'motorbike', 'person', 'pottedplant',
                         'sheep', 'sofa', 'train', 'tvmonitor'))
    colormap = [(0,0,0),(0.5,0,0),(0,0.5,0),(0.5,0.5,0),(0,0,0.5),(0.5,0,0.5),(0,0.5,0.5), 
                    (0.5,0.5,0.5),(0.25,0,0),(0.75,0,0),(0.25,0.5,0),(0.75,0.5,0),(0.25,0,0.5), 
                    (0.75,0,0.5),(0.25,0.5,0.5),(0.75,0.5,0.5),(0,0.25,0),(0.5,0.25,0),(0,0.75,0), 
                    (0.5,0.75,0),(0,0.25,0.5)]
    cmap = colors.ListedColormap(colormap)
    bounds=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21]
    norm = colors.BoundaryNorm(bounds, cmap.N)

    ax1.set_title('gt')
    ax1.imshow(gt, cmap=cmap, norm=norm)

    ax2.set_title('pred')
    ax2.imshow(pred, cmap=cmap, norm=norm)

    plt.show()

def main():
    """Create the model and start the evaluation process."""
    args = get_arguments()

    gpu0 = args.gpu

    model = Res_Deeplab(num_classes=args.num_classes)
    
    saved_state_dict = torch.load(args.restore_from)
    model.load_state_dict(saved_state_dict)

    model.eval()
    model.cuda(gpu0)

    testloader = data.DataLoader(VOCDataSet(args.data_dir, args.data_list, crop_size=(505, 505), mean=IMG_MEAN, scale=False, mirror=False), 
                                    batch_size=1, shuffle=False, pin_memory=True)

    interp = nn.Upsample(size=(505, 505), mode='bilinear')
    data_list = []

    for index, batch in enumerate(testloader):
        print('%d processd'%(index))
        images, label, size, name = batch
        images = Variable(images, volatile=True)
        h, w, c = size[0].numpy()
        images075 = nn.Upsample(size=(int(h*0.75), int(w*0.75)), mode='bilinear')(images)
        images05 = nn.Upsample(size=(int(h*0.5), int(w*0.5)), mode='bilinear')(images)

        out100 = model(images.cuda(args.gpu))
        #print("size of out100:", out100.size())
        out075 = model(images075.cuda(args.gpu))

        #print("size of out075:", out075.size())
        out05 = model(images05.cuda(args.gpu))

        #print("size of out05:", out05.size())
        o_h, o_w = out100.size()[2:]
        interpo1 = nn.Upsample(size=(o_h, o_w), mode='bilinear')
        out_max = torch.max(torch.stack([out100, interpo1(out075), interpo1(out05)]), dim=0)[0]

        output = interp(out_max).cpu().data[0].numpy()
        

        output = output[:,:h,:w]

        output = output.transpose(1,2,0)
        output = np.asarray(np.argmax(output, axis=2), dtype=np.int)

        gt = np.asarray(label[0].numpy()[:h,:w], dtype=np.int)

        #print("size of gt:", gt.shape)
        # show_all(gt, output)
        data_list.append([gt.flatten(), output.flatten()])

    get_iou(data_list, args.num_classes)


if __name__ == '__main__':
    main()
