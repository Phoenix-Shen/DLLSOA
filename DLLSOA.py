import torch.nn as nn
import torch.utils.data as data
from torch.optim import Adam
import numpy as np
import torch as t
from utils import calculate_grad_norm, get_weight_num, calculate_weight_norm
import random
from tensorboardX import SummaryWriter
from copy import deepcopy
from dataset import load_mnist
from model import resnet18
import random


class LocalClient(object):
    def __init__(self,
                 local_model: nn.Module,
                 train_loader: data.DataLoader,
                 test_loader: data.DataLoader,
                 loss_func: nn.Module,
                 comp_strategy: str,
                 lr: float,
                 ep_num: int,
                 sub_carrier_num: int,
                 device: t.device):
        # save parameters as member variables
        self.model = local_model.to(device)
        self.train_loader = train_loader
        self.test_loader = test_loader
        self.comp_strategy = comp_strategy
        self.lr = lr
        self.ep_num = ep_num
        self.device = device
        self.sub_carrier_num = sub_carrier_num
        # init optimizer and loss function
        self.optimizer = Adam(self.model.parameters(), self.lr)
        self.loss_func = loss_func

    def train(self,):
        """
        Train the local model using the given train_loader for a round
        -------
        Parameters:
            None
        Returns:
            the loss of the trainset.
        """
        for ep in range(self.ep_num):
            ep_loss = []
            for (X, y) in self.train_loader:
                X = X.to(self.device)
                y = y.to(self.device)
                y_hat = self.model.forward(X)
                loss = self.loss_func.forward(y_hat, y)
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
                ep_loss.append(loss.item())

        return np.mean(ep_loss)

    def test(self,):
        """
        start the test procedure
        -------
        Parameters:
            None
        Returns:
            the loss and accuracy of the testset.
        """
        sum_loss = []
        correct = 0
        # start the iteration
        with t.no_grad():
            for (X, y) in self.test_loader:
                y_hat = self.model.forward(X)
                loss = self.loss_func.forward(y_hat, y)
                sum_loss.append(loss.item())
                y_prediction = y_hat.data.max(1, keepdim=True)[1]
                correct += y_prediction.eq(y.data.view_as(y_prediction)
                                           ).long().cpu().sum()

        return np.mean(sum_loss), 100.*correct / len(self.test_loader.dataset)

    def generate_mask(self):
        """
        generates the mask according to the subcarrier number
        ------
        Returns:
            a list of the parameters that should be chosen
        """
        if self.comp_strategy == "random":
            param_keys = []
            for name, _ in self.model.named_parameters():
                if "weight" in name:
                    param_keys.append(name)
            random.shuffle(param_keys)
            return param_keys[:self.sub_carrier_num]
        elif self.comp_strategy == "weight":
            weight_dict = calculate_weight_norm(self.model)
            weight_keys = [item[0]
                           for item in weight_dict][:self.sub_carrier_num]
            return weight_keys
        elif self.comp_strategy == "grad":
            grad_dict = calculate_grad_norm(self.model)
            grad_keys = [item[0] for item in grad_dict][:self.sub_carrier_num]
            return grad_keys


class DLLSOA(object):
    def __init__(self, args: dict):
        # save arguments to member variables
        if args["model_name"] == "resnet-18":
            net = resnet18.Resnet18()
        elif args["model_name"] == "CNN":
            net = None  # not implemented yet
        else:
            raise ValueError(
                "only support resnet-18 and CNN, pls check the model_name")
        self.device = t.device(
            "cuda") if args["cuda"] and t.cuda.is_available() else t.device("cpu")
        self.num_clients = args["num_clients"]
        # split datasets
        dataloader_allusr, train_loader, test_loader = load_mnist(
            args["iid"], args["num_clients"], args["batch_size"],)
        # get the subcarrier num
        weight_num = get_weight_num(net)
        if args["sub_carrier_strategy"] == "no-limit":
            sub_carrier_nums = [weight_num for _ in range(self.num_clients)]
        elif args["sub_carrier_strategy"] == "restricted-1":
            sub_carrier_nums = [weight_num for _ in range(self.num_clients/3)]
            sub_carrier_nums += [int(weight_num*0.8)
                                 for _ in range(self.num_clients/3)]
            sub_carrier_nums += [int(weight_num*0.6)
                                 for _ in range(self.num_clients/3)]
            random.shuffle(sub_carrier_nums)
        elif args["sub_carrier_strategy"] == "restricted-2":
            sub_carrier_nums = [weight_num for _ in range(self.num_clients/4)]
            sub_carrier_nums += [int(weight_num*0.8)
                                 for _ in range(self.num_clients/4)]
            sub_carrier_nums += [int(weight_num*0.7)
                                 for _ in range(self.num_clients/4)]
            sub_carrier_nums += [int(weight_num*0.6)
                                 for _ in range(self.num_clients/4)]
            random.shuffle(sub_carrier_nums)
        else:
            raise ValueError(
                "only support no-limit, restricted-1, restricted-2")

        # create clients
        self.clients = [
            LocalClient(
                deepcopy(net),
                dataloader_allusr[i],
                test_loader,
                nn.CrossEntropyLoss(),
                args["comp_strategy"],
                args["lr"],
                args["ep_num"],
                sub_carrier_nums[i],
                self.device,
            )
            for i in range(self.num_clients)
        ]
