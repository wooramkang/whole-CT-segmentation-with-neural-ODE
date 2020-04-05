import os
import glob
import random
from torch.utils.tensorboard import SummaryWriter
import torch
import torch.utils.data
import torch.nn as nn
import PIL
import skimage.measure
import numpy as np
import matplotlib.pyplot as plt

from tqdm import tqdm, tqdm_notebook
from models import ConvODEUNet, ConvResUNet, ODEBlock, Unet
from dataloader import GLaSDataLoader

torch.manual_seed(0)
train_img_idr = os.listdir('/project/NANOSCOPY/Submit/Submit/image_integ/')
train_mask_idr = os.listdir('/project/NANOSCOPY/Submit/Submit/Zen_integ/')
val_img_idr = os.listdir('/project/NANOSCOPY/Submit/Submit/image_integ_val/')
val_mask_idr = os.listdir('/project/NANOSCOPY/Submit/Submit/Zen_integ_val/')

valset = GLaSDataLoader((25, 25), dataset_repeat=1, images=val_img_idr, masks=val_mask_idr ,validation=True, Image_fname ='/project/NANOSCOPY/Submit/Submit/image_integ_val/',
                        Mask_fname ='/project/NANOSCOPY/Submit/Submit/Zen_integ_val/')
VAL_BATCH_SIZE = 1000
valloader = torch.utils.data.DataLoader(valset, batch_size=VAL_BATCH_SIZE, shuffle=True, num_workers=4)

#try:
device = torch.device('cuda')
#except:
    #device = torch.device('cpu')
output_dim = 28
net = ConvODEUNet(num_filters=32, output_dim=output_dim, time_dependent=True, non_linearity='lrelu', adjoint=True, tol=1e-5)
net.to(device)

for m in net.modules():
    if isinstance(m, torch.nn.Conv2d):
        torch.nn.init.kaiming_normal_(m.weight)
        torch.nn.init.constant_(m.bias, 0)

def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

print(count_parameters(net))
class RMSELoss(nn.Module):
    def __init__(self):
        super().__init__()
        self.mse = nn.MSELoss()
        
    def forward(self,yhat,y):
        return torch.sqrt(self.mse(yhat,y))

criterion = torch.nn.BCEWithLogitsLoss()
val_criterion = torch.nn.BCEWithLogitsLoss()
MSE = torch.nn.MSELoss()
RMSE = RMSELoss()
optimizer = torch.optim.Adam(net.parameters(), lr=1e-4)
torch.backends.cudnn.benchmark = True
losses = []
val_losses = []
nfe = [[],[],[],[],[],[],[],[],[]]# if TRAIN_UNODE else None

i = 1
tfboard_path = 'runs/new_zernik_coff_val_' + str(i)

from torch.nn.functional import cosine_similarity
filename = 'best_retriaval_model.pt'

try:
    net = torch.load(filename)
    print("loaded pretrained model")
except:
    print("no pretrained model")

accumulate_batch = 1  # mini-batch size by gradient accumulation
accumulated = 0


zen_coff_GT = [0 for i in range(28)]
zen_coff_output = [0 for i in range(28)]
zen_error = [0 for i in range(28)]
err_dist = [ 0 for i in range(10000)]

accumulated = 0
step_size = 10
count_step = 0

count = 0
running_loss = 0.0
total_RMSE = 0.0

lr = 1e-3
for param_group in optimizer.param_groups:
    param_group['lr'] = lr

with torch.no_grad():
    for data in valloader:
        count_step = count_step + 1
        if (count_step % step_size) == 0:
            print(count_step)

        inputs, labels = data[0].cuda(), data[1].cuda()
        outputs = net(inputs)
        MSEloss = MSE (outputs, labels)
        #RMSEloss = RMSE(outputs, labels)

        outputs = outputs.cpu().clone().numpy()
        labels = labels.cpu().clone().numpy()
        for idx in range(outputs.shape[0]):
            zen_coff_GT = [ zen_coff_GT[i] + labels[idx][i] for i in range(28)]
            zen_coff_output = [zen_coff_output[i] + outputs[idx][i] for i in range(28)]
            zen_error = [ zen_error[i] + np.abs(labels[idx][i] - outputs[idx][i])  for i in range(28)]            

        err_dist[int(MSEloss.item() * 1000)] = err_dist[ int(MSEloss.item() * 1000)] + 1
            
    zen_error = [ i / len(valloader)  for i in zen_error ]        
    max_GT = max(zen_coff_output)
    min_GT = min(zen_coff_output)
    #zen_coff_output = [ 2 * ((i - min_GT ) / (max_GT - min_GT)) - 1 for i in zen_coff_output]
    #zen_coff_GT = [ 2 * ((i - min_GT) /  (max_GT - min_GT)) - 1 for i in zen_coff_GT]

    err_dist = [ i/ len(valloader) for i in err_dist ]
    err_dist = np.array(err_dist)
    #err_dist = err_dist - min(err_dist)
    #err_dist = err_dist / (max(err_dist) - min(err_dist))        

    poi_dist = [0 for i in range(1000)]
    for s in range(10000):
        s = np.random.poisson(16)/ 3125
        poi_dist[int(s*1000)] = poi_dist[int(s*1000)] + 1
    poi_dist = np.array(poi_dist)
    #poi_dist = poi_dist - min(poi_dist)
    #poi_dist = poi_dist / (max(poi_dist) - min(poi_dist))

    axis_x = [ i/1000 for i in range(1000)]
    plt.figure()
    plt.plot(axis_x[0:1000], err_dist[0:1000], color='r', label ='loss with noise')
    plt.plot(axis_x[0:1000], poi_dist[0:1000], color='b', label ='poisson_noise')
    plt.savefig("output_error_dist.png")
    plt.show()

    plt.figure()
    plt.plot(axis_x[0:1000], err_dist[0:1000], color='r', label ='loss with noise')
    plt.savefig("output_only_error_dist.png")
    plt.show()

    Zen_range = range(0,28)

    plt.figure()
    plt.plot(Zen_range, zen_coff_output, color='r', label ='output')
    plt.plot(Zen_range, zen_coff_GT, color='b', label='GT')
    plt.savefig("output_GT_with_dist.png")
    plt.show()

    plt.figure()
    plt.plot(Zen_range, zen_error, color='r', label ='err')
    plt.savefig("output_GT_with_MAE.png")
    plt.show()
                    