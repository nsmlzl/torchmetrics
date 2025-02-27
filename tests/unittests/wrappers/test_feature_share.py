# Copyright The Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import pytest
import torch
from torchmetrics import MetricCollection
from torchmetrics.image import (
    FrechetInceptionDistance,
    InceptionScore,
    KernelInceptionDistance,
    LearnedPerceptualImagePatchSimilarity,
    StructuralSimilarityIndexMeasure,
)
from torchmetrics.wrappers import FeatureShare


@pytest.mark.parametrize(
    "metrics",
    [
        [FrechetInceptionDistance(), InceptionScore(), KernelInceptionDistance()],
        {"fid": FrechetInceptionDistance(), "is": InceptionScore(), "kid": KernelInceptionDistance()},
    ],
)
def test_initialization(metrics):
    """Test that the feature share wrapper can be initialized."""
    fs = FeatureShare(metrics)
    assert isinstance(fs, MetricCollection)
    assert len(fs) == 3


def test_error_on_missing_feature_network():
    """Test that an error is raised when the feature network is missing."""
    with pytest.raises(AttributeError, match="Tried to extract the network to share from the first metric.*"):
        FeatureShare([StructuralSimilarityIndexMeasure(), FrechetInceptionDistance()])

    with pytest.raises(AttributeError, match="Tried to set the cached network to all metrics, but one of the.*"):
        FeatureShare([FrechetInceptionDistance(), StructuralSimilarityIndexMeasure()])


def test_warning_on_mixing_networks():
    """Test that a warning is raised when the metrics use different networks."""
    with pytest.warns(UserWarning, match="The network to share between the metrics is not.*"):
        FeatureShare([FrechetInceptionDistance(), InceptionScore(), LearnedPerceptualImagePatchSimilarity()])


def test_feature_share_speed():
    """Test that the feature share wrapper is faster than the metric collection."""
    mc = MetricCollection([FrechetInceptionDistance(), InceptionScore(), KernelInceptionDistance()])
    fs = FeatureShare([FrechetInceptionDistance(), InceptionScore(), KernelInceptionDistance()])
    x = torch.randint(255, (1, 3, 64, 64), dtype=torch.uint8)

    import time

    start = time.time()
    for _ in range(10):
        x = torch.randint(255, (1, 3, 64, 64), dtype=torch.uint8)
        mc.update(x, real=True)
    end = time.time()
    mc_time = end - start

    start = time.time()
    for _ in range(10):
        x = torch.randint(255, (1, 3, 64, 64), dtype=torch.uint8)
        fs.update(x, real=True)
    end = time.time()
    fs_time = end - start

    assert fs_time < mc_time, "The feature share wrapper should be faster than the metric collection."


@pytest.mark.skipif(not torch.cuda.is_available(), reason="test requires GPU machine")
def test_memory():
    """Test that the feature share wrapper uses less memory than the metric collection."""
    base_memory = torch.cuda.memory_allocated()

    fid = FrechetInceptionDistance().cuda()
    inception = InceptionScore().cuda()
    kid = KernelInceptionDistance().cuda()

    memory_before_fs = torch.cuda.memory_allocated()
    assert memory_before_fs > base_memory, "The memory usage should be higher after initializing the metrics."

    torch.cuda.empty_cache()

    FeatureShare([fid, inception, kid]).cuda()
    memory_after_fs = torch.cuda.memory_allocated()

    assert (
        memory_after_fs > base_memory
    ), "The memory usage should be higher after initializing the feature share wrapper."
    assert (
        memory_after_fs < memory_before_fs
    ), "The memory usage should be higher after initializing the feature share wrapper."


def test_same_result_as_individual():
    """Test that the feature share wrapper gives the same result as the individual metrics."""
    fid = FrechetInceptionDistance(feature=768)
    inception = InceptionScore(feature=768)
    kid = KernelInceptionDistance(feature=768, subset_size=10, subsets=2)

    fs = FeatureShare([fid, inception, kid])

    x = torch.randint(255, (50, 3, 64, 64), dtype=torch.uint8)
    fs.update(x, real=True)
    fid.update(x, real=True)
    inception.update(x)
    kid.update(x, real=True)
    x = torch.randint(255, (50, 3, 64, 64), dtype=torch.uint8)
    fs.update(x, real=False)
    fid.update(x, real=False)
    inception.update(x)
    kid.update(x, real=False)

    fs_res = fs.compute()
    fid_res = fid.compute()
    inception_res = inception.compute()
    kid_res = kid.compute()

    assert fs_res["FrechetInceptionDistance"] == fid_res
    assert fs_res["InceptionScore"][0] == inception_res[0]
    assert fs_res["InceptionScore"][1] == inception_res[1]
    assert fs_res["KernelInceptionDistance"][0] == kid_res[0]
    assert fs_res["KernelInceptionDistance"][1] == kid_res[1]
