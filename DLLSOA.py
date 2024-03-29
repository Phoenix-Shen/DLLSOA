import torch.nn as nn
import torch.utils.data as data
from torch.optim import Adam
import numpy as np
import torch as t
from utils import (calculate_grad_norm,
                   get_weight_num,
                   calculate_weight_norm,
                   compute_power_coeff,
                   compute_alpha,
                   aggregation,
                   weight_init,
                   init_w,
                   calculate_E,
                   gen_topo,
                   create_folder,
                   calculate_agg_var,
                   calculate_data_amount)
import random
from tensorboardX import SummaryWriter
from copy import deepcopy
from dataset import load_mnist, load_cifar10
from model import resnet18
import random
from numpy import ndarray
import time
import os
import yaml
from tqdm import tqdm


class LocalClient(object):
    def __init__(self,
                 id: int,
                 local_model: nn.Module,
                 train_loader: data.DataLoader,
                 test_loader: data.DataLoader,
                 loss_func: nn.Module,
                 comp_strategy: str,
                 lr: float,
                 ep_num: int,
                 sub_carrier_num: int,
                 device: t.device,
                 channel_gain: ndarray,
                 pow_limit: bool,
                 pow_allow_stg: str):
        # save parameters as member variables
        self.id = id
        self.model = local_model.to(device)
        self.train_loader = train_loader
        self.test_loader = test_loader
        self.comp_strategy = comp_strategy
        self.lr = lr
        self.ep_num = ep_num
        self.device = device
        self.sub_carrier_num = sub_carrier_num
        self.pow_limit = pow_limit
        self.pow_allow_stg = pow_allow_stg
        # init optimizer and loss function
        self.optimizer = Adam(self.model.parameters(), self.lr)
        self.loss_func = loss_func
        self.model.apply(weight_init)
        # init channel gain
        self.channel_gain = channel_gain

    def rcv_params(self, model_params: dict, xi_neighbors: ndarray, weight_neighbors: ndarray, amendment_strategy: str):
        """
        receive the parameters from the neighbors
        ------
        Parameters:
            model_params:dict, the sum of neighboring clients information through over-the-air aggregation (already added noise)
            xi_neighbors: the xi of the neighbors
            weight_neighbors: the weight of the neighbors
        Returns:
            None
        """
        # compute alpha
        if amendment_strategy == "eq5":
            alpha = compute_alpha(self.id, xi_neighbors.copy(),
                                  None, self.pow_limit)
        elif amendment_strategy == "eq6":
            alpha = compute_alpha(self.id, xi_neighbors.copy(),
                                  weight_neighbors.copy(), self.pow_limit)
        else:
            raise ValueError("Unsupported value, only support eq5 and eq6")

        if model_params is not None:
            # begin aggregation
            model_params = {k: v*alpha for k, v in model_params.items()}
            # add its' own parameters
            model_params = {
                k: model_params[k]+self.model.state_dict()[k]*weight_neighbors[self.id] for k in model_params.keys()}
            # finally load the state dictionary
            self.model.load_state_dict(model_params, strict=False)

    def send_params(self, component_keys: list[str], W: float, channel_gain: ndarray, beta: float, beta_noise: float):
        """
        get the parameters according to the channel conditions
        ------
        Parameters:
            component_keys: the key of parameters, i.e. the mask in the paper
            W: float, the W_{ij} in equation (3), W is the connectivity matrix
            channel_gain: the channel gain of the specified local device
            beta: the estimation factor of the E
            beta_noise: the Gaussian noise's variance of beta
        Returns:
            model_param:the specified parameters after power coefficient adjustments
            xi: the computed xi
        """
        # start the training procedure

        #
        with t.no_grad():
            # compute the power allocation coefficients b_ij^t(k) first
            weight_norm = calculate_weight_norm(self.model, component_keys)
            weight_norm_val = np.array(list(weight_norm.values()))
            # compute E
            beta = np.random.normal(0.0, beta_noise)+beta
            E = calculate_E(W, weight_norm_val, channel_gain, beta)
            b, xi = compute_power_coeff(
                E, W, channel_gain, weight_norm_val, self.pow_limit, self.pow_allow_stg)
            # get the parameters according to the mask (here we use key to read the parameters)
            all_keys = self.model.state_dict().keys()
            model_param = {}
            for key in all_keys:
                if key in component_keys:
                    model_param[key] = self.model.state_dict()[key]
            # multiply the weight by the power allocation coefficients and the channel gain
            for idx, key in enumerate(component_keys):
                model_param[key] = model_param[key]*b[idx]*channel_gain[idx]
            # finally, return the processed parameters
            return model_param, xi

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
                X = X.to(self.device)
                y = y.to(self.device)
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
                if "weight" in name or "bias" in name:
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
        if args["dataset"] == "MNIST":
            num_channels = 1
            num_classes = 10
        elif args["dataset"] == "CIFAR10":
            num_channels = 3
            num_classes = 10
        if args["model_name"] == "resnet-18":
            net = resnet18.Resnet18(num_channels, num_classes)
        elif args["model_name"] == "CNN":
            net = None  # not implemented yet
        else:
            raise ValueError(
                "only support resnet-18 and CNN, pls check the model_name")
        self.device = t.device(
            "cuda") if args["cuda"] and t.cuda.is_available() else t.device("cpu")
        if self.device == t.device("cuda"):
            t.backends.cudnn.benchmark = True
        self.num_clients = args["num_clients"]
        self.sigma = args["sigma"]
        self.amendment_strategy = args["amendment_strategy"]
        self.train_epoch = args["train_epoch"]
        self.beta = args["beta"]
        self.pow_limit = args["pow_limit"]
        self.seed = args["seed"]
        self.beta_noise = args["beta_noise"]
        self.aggregation_mode = args["aggregation_mode"]
        self.disable_com = args["disable_com"]
        np.random.seed(self.seed)
        # split datasets
        if args["dataset"] == "MNIST":
            dataloader_allusr, train_loader, test_loader = load_mnist(
                args["iid"], args["num_clients"], args["batch_size"],)
        elif args["dataset"] == "CIFAR10":
            dataloader_allusr, train_loader, test_loader = load_cifar10(
                args["iid"], args["num_clients"], args["batch_size"],)
        else:
            raise ValueError(
                "only support MNIST and CIFAR10")

        # get the subcarrier num
        weight_num = get_weight_num(net)
        # MNIST
        if args["dataset"] == "MNIST":
            if args["sub_carrier_strategy"] == "no-limit":
                sub_carrier_nums = [
                    weight_num for _ in range(self.num_clients)]
            elif args["sub_carrier_strategy"] == "restricted-1":
                sub_carrier_nums = [int(weight_num*0.5)
                                    for _ in range(self.num_clients)]
                random.shuffle(sub_carrier_nums)
            elif args["sub_carrier_strategy"] == "restricted-2":
                sub_carrier_nums = [int(weight_num*0.75)
                                    for _ in range(int(self.num_clients/3))]
                sub_carrier_nums += [int(weight_num*0.5)
                                     for _ in range(int(self.num_clients/3))]
                sub_carrier_nums += [int(weight_num*0.25)
                                     for _ in range(int(self.num_clients/3))]
                random.shuffle(sub_carrier_nums)
            elif args["sub_carrier_strategy"] == "restricted-3":
                sub_carrier_nums = [int(weight_num*0.1)
                                    for _ in range(self.num_clients)]
                random.shuffle(sub_carrier_nums)
            else:
                raise ValueError(
                    "only support no-limit, restricted-1, restricted-2,restricted-3")
        # CIFAR10
        elif args["dataset"] == "CIFAR10":
            if args["sub_carrier_strategy"] == "no-limit":
                sub_carrier_nums = [
                    weight_num for _ in range(self.num_clients)]
            elif args["sub_carrier_strategy"] == "restricted-1":
                sub_carrier_nums = [int(weight_num*0.6)
                                    for _ in range(self.num_clients)]
                random.shuffle(sub_carrier_nums)
            elif args["sub_carrier_strategy"] == "restricted-2":
                sub_carrier_nums = [int(weight_num*0.8)
                                    for _ in range(int(self.num_clients/3))]
                sub_carrier_nums += [int(weight_num*0.6)
                                     for _ in range(int(self.num_clients/3))]
                sub_carrier_nums += [int(weight_num*0.4)
                                     for _ in range(int(self.num_clients/3))]
                random.shuffle(sub_carrier_nums)
            elif args["sub_carrier_strategy"] == "restricted-3":
                sub_carrier_nums = [int(weight_num*0.3)
                                    for _ in range(self.num_clients)]
                random.shuffle(sub_carrier_nums)
            else:
                raise ValueError(
                    "only support no-limit, restricted-1, restricted-2,restricted-3")
        # create clients
        self.clients = [
            LocalClient(
                i,
                deepcopy(net),
                dataloader_allusr[i],
                test_loader,
                nn.CrossEntropyLoss(),
                args["comp_strategy"],
                args["lr"],
                args["ep_num"],
                sub_carrier_nums[i],
                self.device,
                np.random.rayleigh(
                    1., size=(self.num_clients,
                              sub_carrier_nums[i])),
                self.pow_limit,
                args["pow_allocation_strategy"],
            )
            for i in range(self.num_clients)
        ]
        # init some variables such as connetivity matrix
        self.init_weight()
        self.xi = np.zeros((self.num_clients, self.num_clients))
        # tensorboardX
        log_dir = os.path.join(args["log_dir"], args["dataset"], time.strftime(
            "%Y-%m-%d-%H-%M-%S", time.localtime()))
        create_folder(log_dir)
        self.writer = SummaryWriter(log_dir)
        # save the configuration as a dictionary
        with open(os.path.join(log_dir, "config.yaml"), "w") as f:
            yaml.dump(args, f)

    def init_weight(self,):
        """
        initialize the adjacency matrix and the weight matrix w
        ------
        Parameters:
            None
        Returns:
            None
        """
        # init w
        topo = gen_topo(self.num_clients)
        self.W = init_w(topo)

    def train(self):
        """
        begin the training procedure
        ------
        Parameters:
            None
        Returns:
            None
        """
        # here simply use for loop instead of multiprocessing
        # todo: use multiprocessing
        print("training begin...")
        #print("the randomly generated W is: \n", self.W)
        for ep in tqdm(range(self.train_epoch)):
            # local training
            self.init_weight()
            losses = [client.train() for client in self.clients]
            data_amount = 0
            data_size = 0
            if not self.disable_com:
                for i in range(self.num_clients):
                    # 1. generate mask of components
                    mask = self.clients[i].generate_mask()
                    channel_gains = self.clients[i].channel_gain
                    rcv_models = []
                    # 2. send the mask to all neighbors and receive parameters
                    for j in range(self.num_clients):
                        if self.W[i][j] != 0. and i != j:
                            model, self.xi[i][j] = self.clients[j].send_params(
                                mask, self.W[i][j], channel_gains[i], self.beta, self.beta_noise)
                            rcv_models.append(model)
                    # 3. begin aggregation
                    sigma = calculate_agg_var(
                        self.W, i, self.sigma, self.aggregation_mode)
                    processed_model = aggregation(
                        rcv_models, sigma)
                    # 4. perform gradient descent and update parameters
                    self.clients[i].rcv_params(
                        processed_model, self.xi[i], self.W[i], self.amendment_strategy)
                    # 5. calculate the communication data amount
                    size, amount = calculate_data_amount(rcv_models)
                    data_size += size
                    data_amount += amount
            # Tensorboard logs and print loss
            test_loss_acc = [client.test() for client in self.clients]
            [self.writer.add_scalar("test_loss_client_{}".format(
                i), test_loss_acc[i][0], ep) for i in range(len(test_loss_acc))]
            [self.writer.add_scalar("test_acc_client_{}".format(
                i), test_loss_acc[i][1], ep) for i in range(len(test_loss_acc))]
            [self.writer.add_scalar("train_loss_client_{}".format(
                i), losses[i], ep) for i in range(len(losses))]
            self.writer.add_scalar("mean_train_loss", np.mean(losses), ep)
            self.writer.add_scalar("mean_test_loss", np.mean(
                [test_loss_acc[i][0] for i in range(len(test_loss_acc))]), ep)
            self.writer.add_scalar("mean_test_acc", np.mean(
                [test_loss_acc[i][1] for i in range(len(test_loss_acc))]), ep)
            self.writer.add_scalar("data_size (MB)", data_size/1024/1024, ep)
            self.writer.add_scalar("data_amount (M)", data_amount/1000000, ep)
            print(
                f"ep:[{ep}/{self.train_epoch}],train_loss:{losses},test_loss_acc:{test_loss_acc}")

    def test(self):
        """
        begin the test procedure
        """
        pass
