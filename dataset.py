import torchvision as tv

from torch.utils import data
import numpy as np
from torch.utils.data import DataLoader, Dataset
import torchvision.transforms as transforms


class DatasetSplit(Dataset):
    def __init__(self, dataset, idxs):
        super().__init__()
        self.dataset = dataset
        self.idxs = list(idxs)

    def __len__(self):
        return len(self.idxs)

    def __getitem__(self, item):
        image, label = self.dataset[self.idxs[item]]
        return image, label


def load_mnist(iid: bool, num_users: int, batch_size: int):
    """
    Load the MNIST dataset
    -------
    Parameters:
    --------
    iid: bool
        whether the data is iid or not
    num_users: int
        the number of users
    batch_size: int
        the batch size
    Returns:
    --------
    list[DataLoader]:
        the dataloader of the all users
    Dataset
        the whole train and test dataset
    """
    trans_mnist = tv.transforms.Compose(
        [tv.transforms.ToTensor(), tv.transforms.Normalize((0.1307,), (0.3081,))])
    dataset_train = tv.datasets.MNIST(
        root=r'data', train=True, transform=trans_mnist, download=True)
    dataset_test = tv.datasets.MNIST(
        root=r'data', train=False, transform=trans_mnist, download=True)
    # if iid:
    if iid:
        dict_users = mnist_iid(dataset_train, num_users)
    else:
        dict_users = mnist_noniid(dataset_train, num_users)

    datasets_allusr = [DatasetSplit(dataset_train, dict_users[key])
                       for key in dict_users.keys()]
    dataloader_allusr = [DataLoader(
        datasets_allusr[i], batch_size, shuffle=True) for i in range(num_users)]
    test_loader = DataLoader(dataset_test, batch_size, shuffle=False)
    train_loader = DataLoader(dataset_train, batch_size, shuffle=False)

    return dataloader_allusr, train_loader, test_loader


def mnist_iid(dataset: data.Dataset, num_users: int) -> dict:
    """
    Split the MNIST dataset into IID data
    -----
    parameters:
    --------
    dataset: data.Dataset
        the MNIST dataset
    num_users: int
        the number of users
    --------
    Returns:
    --------
    dict:
        the index IID data of each user
    """
    num_items = int(len(dataset)/num_users)

    dict_users, all_idxs = {}, [i for i in range(len(dataset))]

    for i in range(num_users):
        dict_users[i] = set(np.random.choice(
            all_idxs, num_items, replace=False))
        all_idxs = list(set(all_idxs)-dict_users[i])
    return dict_users


def mnist_noniid(dataset: data.Dataset, num_users: int) -> dict:
    """
    Split the MNIST dataset into non-IID data
    -----
    parameters:
    --------
    dataset: data.Dataset
        the MNIST dataset
    num_users: int
        the number of users
    --------
    Returns:
    --------
    dict:
        the index non-IID data of each user
    """
    # split the train MNIST dataset into 200 groups, each group contains 300 samples
    num_shards, num_imgs = 200, 300  # 200*300 = 60000
    idx_shard = [i for i in range(num_shards)]
    dict_users = {i: np.array([], dtype=np.int64) for i in range(num_users)}

    idxs = np.arange(num_shards*num_imgs)

    labels = dataset.targets.numpy()

    # sort labels to ensure non-iid
    idx_labels = np.vstack((idxs, labels))
    idx_labels = idx_labels[:, idx_labels[1, :].argsort()]
    # sample index accroding to the arrangement of digital 1-9
    idxs = idx_labels[0, :]

    # divide and assign
    for i in range(num_users):
        rand_set = set(np.random.choice(
            idx_shard, int(num_shards/num_users), replace=False))
        idx_shard = list(set(idx_shard)-rand_set)
        # concat
        for rand in rand_set:
            dict_users[i] = np.concatenate(
                (dict_users[i], idxs[rand*num_imgs:(rand+1)*num_imgs]), axis=0)
    return dict_users


def load_cifar10(iid: bool, num_users: int, batch_size: int):
    """
    Load the CIFAR-10 dataset
    -------
    Parameters:
    --------
    iid: bool
        whether the data is iid or not
    num_users: int
        the number of users
    batch_size: int
        the batch size
    Returns:
    --------
    list[DataLoader]:
        the dataloader of the all users
    Dataset
        the whole train and test dataset
    """
    transform_train = transforms.Compose([
        transforms.RandomCrop(32, padding=4),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ])

    transform_test = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ])
    dataset_train = tv.datasets.CIFAR10(
        root=r'data', train=True, transform=transform_train, download=True)
    dataset_test = tv.datasets.CIFAR10(
        root=r'data', train=False, transform=transform_test, download=True)
    # if iid:
    if iid:
        dict_users = cifar10_iid(dataset_train, num_users)
    else:
        dict_users = cifar10_noniid(dataset_train, num_users)

    datasets_allusr = [DatasetSplit(dataset_train, dict_users[key])
                       for key in dict_users.keys()]
    dataloader_allusr = [DataLoader(
        datasets_allusr[i], batch_size, shuffle=True) for i in range(num_users)]
    test_loader = DataLoader(dataset_test, batch_size, shuffle=False)
    train_loader = DataLoader(dataset_train, batch_size, shuffle=True)

    return dataloader_allusr, train_loader, test_loader


def cifar10_iid(dataset: data.Dataset, num_users: int) -> dict:
    """
    Split the cifar10 dataset into IID data
    -----
    parameters:
    --------
    dataset: data.Dataset
        the cifar10 dataset
    num_users: int
        the number of users
    --------
    Returns:
    --------
    dict:
        the index IID data of each user
    """
    num_items = int(len(dataset)/num_users)

    dict_users, all_idxs = {}, [i for i in range(len(dataset))]

    for i in range(num_users):
        dict_users[i] = set(np.random.choice(
            all_idxs, num_items, replace=False))
        all_idxs = list(set(all_idxs)-dict_users[i])
    return dict_users


def cifar10_noniid(dataset: data.Dataset, num_users: int) -> dict:
    """
    Split the cifar10 dataset into non-IID data
    -----
    parameters:
    --------
    dataset: data.Dataset
        the cifar10 dataset
    num_users: int
        the number of users
    --------
    Returns:
    --------
    dict:
        the index non-IID data of each user
    """
    # split the train cifar10 dataset into 250 groups, each group contains 200 samples
    num_shards, num_imgs = 250, 200  # 250*200 = 50000
    idx_shard = [i for i in range(num_shards)]
    dict_users = {i: np.array([], dtype=np.int64) for i in range(num_users)}

    idxs = np.arange(num_shards*num_imgs)

    labels = dataset.targets.numpy()

    # sort labels to ensure non-iid
    idx_labels = np.vstack((idxs, labels))
    idx_labels = idx_labels[:, idx_labels[1, :].argsort()]
    # sample index accroding to the arrangement of digital 1-9
    idxs = idx_labels[0, :]

    # divide and assign
    for i in range(num_users):
        rand_set = set(np.random.choice(
            idx_shard, int(num_shards/num_users), replace=False))
        idx_shard = list(set(idx_shard)-rand_set)
        # concat
        for rand in rand_set:
            dict_users[i] = np.concatenate(
                (dict_users[i], idxs[rand*num_imgs:(rand+1)*num_imgs]), axis=0)
    return dict_users
