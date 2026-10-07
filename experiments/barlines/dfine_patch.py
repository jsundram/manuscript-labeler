"""D-FINE on Apple's GPU (MPS): a workaround, applied at import.

transformers' DFineIntegral weights each box edge's bin probabilities with
F.linear(probabilities, project), `project` a 1-D vector. Its backward pass
fails on MPS ("mat2 must be a matrix": pytorch/pytorch#188891, fix in review
as #188931, September 2026). The same sum as a matrix product with
`project` as one column gives identical results (checked: difference 0.0)
and trains on the GPU, about 2.8 times faster than the CPU here.
"""

import torch.nn.functional as F
from transformers.models.d_fine import modeling_d_fine


def _forward(self, pred_corners, project):
    batch_size, num_queries, _ = pred_corners.shape
    p = F.softmax(pred_corners.reshape(-1, self.max_num_bins + 1), dim=1)
    p = (p @ project.to(p.device).unsqueeze(-1)).squeeze(-1).reshape(-1, 4)
    return p.reshape(batch_size, num_queries, -1)


modeling_d_fine.DFineIntegral.forward = _forward
