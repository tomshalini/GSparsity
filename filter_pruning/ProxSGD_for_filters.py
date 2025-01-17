import torch
from torch.optim.optimizer import Optimizer, required
import numpy as np
import gc

class ProxSGD(Optimizer):
    """ProxSGD algorithm for filter purning.
    
    It is an instantiation of the ProxSGD algorithm proposed in `ProxSGD: Training Structured Neural Networks under Regularization and Constraints` (https://openreview.net/forum?id=HygpthEtvr)

    Arguments:
        params (iterable): iterable of parameters to optimize or dicts defining
            parameter groups
        lr (float, optional): learning rate (default: 1e-3)
        momentum (float, optional): momentum (default: 0.9)
        
        delta (float, optional): term added to the denominator to improve
            numerical stability (default: 1e-8)
        beta (float, optional): beta coefficient used for computing
            running averages of the square of the gradient (default:  0.999)
        For the rationale of delta and beta, refer to Adam: A Method for Stochastic Optimization (https://arxiv.org/abs/1412.6980).
        
        weight_decay (float, optional): regularization constant (mu) (default: None)
    """

    def __init__(self, params, lr=0.001, momentum=0.9, weight_decay=None, delta=1e-8, beta=0.999):
        if not 0.0 <= lr <=1:
            raise ValueError("Invalid learning rate: {}".format(lr))
        if not 0.0 <= momentum <=1:
            raise ValueError("Invalid momentum: {}".format(momentum))
        if not 0.0 <= delta:
            raise ValueError("Invalid delta value: {}".format(delta))
        if not 0.0 <= beta < 1:
            raise ValueError("Invalid beta value: {}".format(beta))
        if weight_decay is not None:
            if not 0.0 <= weight_decay:
                raise ValueError("Invalid weight decay value: {}".format(weight_decay))

        defaults = dict(lr=lr,
                        momentum=momentum,
                        delta=delta,
                        weight_decay=weight_decay,
                        beta=beta)
        
        super(ProxSGD, self).__init__(params, defaults)      

    def __setstate__(self, state):
        super(ProxSGD, self).__setstate__(state)
        for group in self.param_groups:
            group.setdefault('amsgrad', False)

    def step(self, closure=None):
        """Performs a single optimization step.

        Arguments:
            closure (callable, optional): A closure that reevaluates the model
                and returns the loss.
        """
        loss = None
        if closure is not None:
            loss = closure()

        for group in self.param_groups:
            for x in group['params']:
                if x.grad is None:
                    continue
                grad = x.grad.data

                if grad.is_sparse:
                    raise RuntimeError('Prox-SGD does not support sparse gradients')

                state = self.state[x]

                # State initialization
                if len(state) == 0:
                    state['step'] = 0
                    # Exponential moving average of gradient values
                    state['v_t'] = torch.zeros_like(x.data)
                    # Exponential moving average of squared gradient values
                    state['r_t'] = torch.zeros_like(x.data)

                v_t, r_t = state['v_t'], state['r_t']

                state['step'] += 1

                momentum = group['momentum']
                beta = group['beta']

                lr = group['lr']

                # Decay the first and second moment running average coefficient
                v_t.mul_(1 - momentum).add_(momentum, grad)
                r_t.mul_(beta).addcmul_(1 - beta, grad, grad)

                bias_correction = 1 - beta ** (state['step'])

                tau = (r_t / bias_correction).sqrt().add_(group['delta'])
                tau = torch.mean(tau)
                
                b  = x - v_t / tau
                b_shape = b.shape
                if group['weight_decay'] is not None:   # Filters are prunable
                    a  = group['weight_decay'] / tau
                    
                    left = torch.norm((b.view(b_shape[0], -1)), p=2, dim=1) #L2 Norm of filters(shape of left: Number of filters)
                    left = torch.clamp(1 - a / left, min=0)
                    left = left.view(left.shape[0], -1) # reshape tensor to 1D (Number of Filters X 1)
                    
                    b = b.view(b.shape[0], -1)  # reshape tensor from shape of #filters X #channels X filter_size  to #Filters X (#channels X filter_size)                    
                    x_hat = torch.mul(left, b)  #Matrix multiplication of norm of filters with b 
                    x_hat = x_hat.view(b_shape)  #reshape back to original weight tensor shape
                else:
                    x_hat = b

                x.data.add_(lr, x_hat-x)
        gc.collect()
        return loss
