# Decentralized Learning with Limited Subcarriers through Over-the-Air Computation

## 方法介绍

### 去中心化模型

考虑去中心化的学习，有$n$个客户端的集合$\mathcal{V}$，有个通信矩阵$\mathcal{W} = (W_{ij})_{n * n}$里面每个元素就代表客户端$i,j$能不能通信。

时间被分为很多同步轮，在每一轮中，每个客户端都汇聚它们邻居节点的信息，然后以本地数据和邻居信息来进行模型更新。

我们总的优化目标还是找到一个参数$\theta$使每个客户端损失的和最小。
$$
\min f(\theta) = \frac{1}{n} \sum_{n=1}^n \mathbb{E}_{\xi_i \sim \mathcal{D}_i}[F_i(\theta,\xi_i)]
$$

在这篇文章中，我们考虑动态的情况，即$\mathcal{W}$是一直在变的，有些节点可能会掉线，有些节点可能会半路加进来。

### 空中汇聚

客户端通过**无线多重访问信道**(MAC）进行通信，并汇聚邻居的信息。

客户端$i$所需要的参数的每个分量(component)都是被认为是由一个子载波承载的，因此，在去中心化学习的第$t$轮中，客户端$i$收到的信号子载波$k$中的信号可以表示为
$$
y_i^t(k) = \sum_{j\in N_i^t} b_{ij}^t(k)h_{ij}^t(k)x_{ij}^t(k)+n_i^t(k)
$$

在第$k$轮的时候，当客户端$j$通过子载波$k$发送给$j$消息的时候，

$b_{ij}^t(k)$是功率放缩因子

$h_{ij}^t(k)$是通道增益

$b_{ij}^t(k)x_{ij}^t(k)$是客户端$j$发送消息到客户端$i$（通过子载波$k$)的功率

$n_i^t(k)$是通道的噪声

$x_{ij}^t(k)$代表客户端$j$在第$t$轮发送消息到客户端$i$（通过子载波$k$)，这个消息是自己本地模型的一部分。

## 我们的方法

### DLLSOOA

由于网络资源是有限的，通常客户端$i$并不能随便获得关于邻居$j$的所有的模型组件（也就是part），客户端$i$肯定期望它自己能够从邻居$j\in N_i^t$这里获得更多信息。

于是我们就有一个**模型组件选择策略**，选择多少组件还是要具体看通道的子载波数量。

#### 定义1 - 模型组件选择

我们有个$d$维的模型$\theta\in \mathbb{R}^d$，和某个模型选择策略$m\in \{0,1\}^d$

于是我们可以选择一些模型的组件$\theta \odot m$，逐元素相乘就是\odot.

特别地，我们假设对于$t$轮，客户端$i$生成一个掩码$m_i^t$，$m_i^t\in \{0,1\}^d$，于是客户端期望从它的邻居收到的组件可以表示为：

$$
\sum_{j\in N_i^t} W_{ij}^t(\theta_j^t \odot m_i^t) = \sum_{j\in N_i^t} W_{ij}^t C_i^t (\theta_j^t)
$$

其中$W_{ij}^t$是在第$t$轮客户端$i,j$之间的权重，$N_i^t = \{ j \vert W_{ij}^t >0 ,j \in \mathcal{V} j \not= i\}$,$\theta_i^t$是在$t$轮客户端$i$的本地模型，$C_i^t (\theta_j^t) = (\theta_j^t \odot m_i^t)$

#### 定义2 - 模型选择误差

其实是个MSE

$$
\begin{aligned}
\mathbb{E} \vert\vert r^t\vert \vert^2&=\sum_{i=1}^n \mathbb{E} \vert\vert r_i^t\vert \vert^2\\
& = \sum_{i=1}^n \mathbb{E} \vert\vert \sum_{j\in N_i^t} W_{ij}^t(C_i^t(\theta_j^t)-\theta_j^t)\vert \vert^2\\
&= \Delta^{(t)}
\end{aligned}
$$

#### 我们模型的学习过程(第$t$轮)

- 1.掩码生成和掩码传输

    首先，客户端$i$根据策略找到需要的$d_i$组件，然后生成一个掩码$m_i^t$，然后将它发给所有的邻居节点$j\in N_i^t$。

    从直觉上来讲，我们期望获得的模型的部分是前$d_i$个本地模型梯度的绝对值最大的那几个值。但是在这里我们的选择是随机的。

- 2.接受并纠正相邻信息的总和

    每个与$i$的邻居$j$会根据掩膜算出需要的成分：$C_i^t (\theta_j^t) = \theta_j^t \odot m_i^t$

    下一步，在理想状态下，我们的客户端$i$会收到到一个每个元素都不为0的变量$\sum_{j\in N_i^t} W_{ij}^tC_i^t(\theta_j^t)$。

    然而，在实际情况下，因为传输功率的限制和噪声的存在，客户端$i$从子载波$k$中收到的东西为

    $$
    (\tilde {R}_i^t)_{I(k)}=y_i^t(k) = \sum_{j\in N_i^t} b_{ij}^t(k)h_{ij}^t(k)x_{ij}^t(k)+n_i^t(k)
    $$

    客户端$i$可以在本地更正$(\tilde {R}_i^t)_{I(k)}$，并取得对$（\sum_{j\in N_i^t} W_{ij}^tC_i^t(\theta_j^t))_{I(k)}$的一个比较不错的估计$(\hat {R}_i^t)_{I(k)}$

    我们使用$(\hat {R}_i^t)_{I(k)}$来进行本地模型的更新

- 3.更新本地模型

    最终，客户端$i$根据邻居的信息通过空中计算更新自己的本地模型，算法1展示了客户端$i$可以接受最多来自$d_i$个子载波的信号，$d_i$是由本地**模型的特性和子载波数量决定的**

#### 收敛性证明

略略略

#### 传输功率分配

- 上一步略过的过程中，我们发现拟合结果受到通信损失MSE的影响，我们在这一小节考虑如何通过进行功率分配来减小MSE。

- 假设通道增益只有发送端才能知道，也就是当客户端$j$发送给客户端$i$的时候，只有$j$知道：$\mathbf{h}_{ij}^t=[h_{ij}(1)^t,\dots,{ij}(d_i)^t]^T$

- 从理论上来讲，如果客户端的功率不限制的话，我们直接将功率因子调整为
    $$
    b_{ij}^t(k) = \frac{W_{ij}^t}{h_{ij}(k)^t}
    $$
    来保证客户端$i$收到的是邻居信息的一个无偏的估计，但是事实总不是如此，实现上述想法很难。
- 所以在每一轮，每个客户端$j\in N_i^t$都需要优化本地的功耗分配，通过子载波$d_i$来传输自己的模型的某些部分,以期望达到下面式子的一个最好的估计：
  $$
    \sum_{j\in N_i^t} W_{ij}^tC_i^t(\theta_j^t)
  $$

#### 注意事项

1. 选择component的粒度是在layer上，也就是Linear1，Conv1
2. 功率分配会影响到模型的精度
3. 空中计算就直接做加法就可以了
4. 梯度的模长或者是参数的二次范数，根据这个来选择哪个模型的组件

#### 问题

1. 数据集要不要拆分，是Identical的还是IID的等等
2. 是否要进行本地训练，本地训练多少轮
3. 矩阵$W$是不是全部是1呢？还是随机生成
4. 功率这方面还要好好讲讲，搞不太懂
5. 神经网络并不是只有卷积层和全连接有参数，这些参数咋办（倾向于忽略），而且参数有weight 和bias，是都选还是怎么滴
6. 打印LOSS的具体细节（关于测试集）
7. 这个“只能接收”具体是哪个地方受限制了？
