# Copyright (c) 2019  PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"
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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import paddle.fluid as fluid
from paddle.fluid.param_attr import ParamAttr
from .search_space_base import SearchSpaceBase
from .base_layer import conv_bn_layer
from .search_space_registry import SEARCHSPACE

__all__ = ["ResNetSpace"]


@SEARCHSPACE.register
class ResNetSpace(SearchSpaceBase):
    def __init__(self,
                 input_size,
                 output_size,
                 block_num,
                 block_mask=None,
                 extract_feature=False,
                 class_dim=1000):
        super(ResNetSpace, self).__init__(input_size, output_size, block_num,
                                          block_mask)
        assert self.block_mask == None, 'ResNetSpace will use origin ResNet as seach space, so use input_size, output_size and block_num to search'
        # self.filter_num1 ~ self.filter_num4 means convolution channel
        self.filter_num1 = np.array([48, 64, 96, 128, 160, 192, 224])  #7 
        self.filter_num2 = np.array([64, 96, 128, 160, 192, 256, 320])  #7
        self.filter_num3 = np.array([128, 160, 192, 256, 320, 384])  #6
        self.filter_num4 = np.array([192, 256, 384, 512, 640])  #5
        # self.repeat1 ~ self.repeat4 means depth of network
        self.repeat1 = [2, 3, 4, 5, 6]  #5
        self.repeat2 = [2, 3, 4, 5, 6, 7]  #6
        self.repeat3 = [2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 20, 24]  #13
        self.repeat4 = [2, 3, 4, 5, 6, 7]  #6
        self.class_dim = class_dim
        self.extract_feature = extract_feature
        assert self.block_num < 5, 'ResNet: block number must less than 5, but receive block number is {}'.format(
            self.block_num)

    def init_tokens(self):
        """
        The initial token.
        return 2 * self.block_num, 2 means depth and num_filter
        """
        init_token_base = [0, 0, 0, 0, 0, 0, 0, 0]
        self.token_len = self.block_num * 2
        return init_token_base[:self.token_len]

    def range_table(self):
        """
        Get range table of current search space, constrains the range of tokens.
        """
        #2 * self.block_num, 2 means depth and num_filter
        range_table_base = [
            len(self.filter_num1), len(self.repeat1), len(self.filter_num2),
            len(self.repeat2), len(self.filter_num3), len(self.repeat3),
            len(self.filter_num4), len(self.repeat4)
        ]
        return range_table_base[:self.token_len]

    def token2arch(self, tokens=None):
        """
        return net_arch function
        """
        if tokens is None:
            tokens = self.init_tokens()

        depth = []
        num_filters = []
        if self.block_num >= 1:
            filter1 = self.filter_num1[tokens[0]]
            repeat1 = self.repeat1[tokens[1]]
            num_filters.append(filter1)
            depth.append(repeat1)
        if self.block_num >= 2:
            filter2 = self.filter_num2[tokens[2]]
            repeat2 = self.repeat2[tokens[3]]
            num_filters.append(filter2)
            depth.append(repeat2)
        if self.block_num >= 3:
            filter3 = self.filter_num3[tokens[4]]
            repeat3 = self.repeat3[tokens[5]]
            num_filters.append(filter3)
            depth.append(repeat3)
        if self.block_num >= 4:
            filter4 = self.filter_num4[tokens[6]]
            repeat4 = self.repeat4[tokens[7]]
            num_filters.append(filter4)
            depth.append(repeat4)

        def net_arch(input):
            conv = conv_bn_layer(
                input=input,
                filter_size=5,
                num_filters=filter1,
                stride=2,
                act='relu',
                name='resnet_conv0')
            for block in range(len(depth)):
                for i in range(depth[block]):
                    conv = self._bottleneck_block(
                        input=conv,
                        num_filters=num_filters[block],
                        stride=2 if i == 0 and block != 0 else 1,
                        name='resnet_depth{}_block{}'.format(i, block))

            if self.output_size == 1:
                conv = fluid.layers.fc(
                    input=conv,
                    size=self.class_dim,
                    act=None,
                    param_attr=fluid.param_attr.ParamAttr(
                        initializer=fluid.initializer.NormalInitializer(0.0,
                                                                        0.01)),
                    bias_attr=fluid.param_attr.ParamAttr(
                        initializer=fluid.initializer.ConstantInitializer(0)))

            return conv

        return net_arch

    def _shortcut(self, input, ch_out, stride, name=None):
        ch_in = input.shape[1]
        if ch_in != ch_out or stride != 1:
            return conv_bn_layer(
                input=input,
                filter_size=1,
                num_filters=ch_out,
                stride=stride,
                name=name + '_conv')
        else:
            return input

    def _bottleneck_block(self, input, num_filters, stride, name=None):
        conv0 = conv_bn_layer(
            input=input,
            num_filters=num_filters,
            filter_size=1,
            act='relu',
            name=name + '_bottleneck_conv0')
        conv1 = conv_bn_layer(
            input=conv0,
            num_filters=num_filters,
            filter_size=3,
            stride=stride,
            act='relu',
            name=name + '_bottleneck_conv1')
        conv2 = conv_bn_layer(
            input=conv1,
            num_filters=num_filters * 4,
            filter_size=1,
            act=None,
            name=name + '_bottleneck_conv2')

        short = self._shortcut(
            input, num_filters * 4, stride, name=name + '_shortcut')

        return fluid.layers.elementwise_add(
            x=short, y=conv2, act='relu', name=name + '_bottleneck_add')