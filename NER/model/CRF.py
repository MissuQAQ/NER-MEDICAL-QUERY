# -*- coding: utf-8 -*-
"""
Created on Thu Aug 20 07:15:03 2020

@author: yyimi
"""

from typing import List, Optional

import torch
import torch.nn as nn

#%%
class CRF(nn.Module):
    '''
    This module implements a conditional random field
    Args:
        num_tags: Number of tags.
        batch_first: Whether the first dimension corresponds to the size of a minibatch.

    Attributes:
        start_transitions (`~torch.nn.Parameter`): Start transition score tensor 
            of size (num_tags,).
        end_transitions (`~torch.nn.Parameter`): End transition score tensor 
            of size (num_tags,).
        transitions (`~torch.nn.Parameter`): Transition score tensor 
            of size (num_tags, num_tags).
    '''
    
    def __init__(self, num_tags: int, batch_first: bool = False):
        
        if num_tags <= 0:
            raise ValueError(f'invalid number of tags: {num_tags}')
        super().__init__()
        self.num_tags = num_tags
        self.batch_first = batch_first
        
        """This module will add the transition probability of <start> and <end> 
        automatically, so dont need to add <start> and <end> on sample manually"""
        self.start_transitions = nn.Parameter(torch.empty(num_tags))
        self.end_transitions = nn.Parameter(torch.empty(num_tags))
        
        
        """ Transistion matrix do not include the <start> and <end> mark """ 
        self.transitions = nn.Parameter(torch.empty(num_tags, num_tags)) 

        self.reset_parameters()
    
    def reset_parameters(self):
        """
        Initialize the transition parameters.
        The parameters will be initialized randomly from a uniform distribution
        between -0.1 and 0.1.
        """
        nn.init.uniform_(self.start_transitions, -0.1, 0.1)
        nn.init.uniform_(self.end_transitions, -0.1, 0.1)
        nn.init.uniform_(self.transitions, -0.1, 0.1)
     
    
    def __repr__(self) :
        return f'{self.__class__.__name__}(num_tags={self.num_tags})'
    
    
    def forward(self, emissions: torch.Tensor, tags: torch.LongTensor,
            mask: Optional[torch.ByteTensor] = None, reduction: str = 'sum'):
        '''
        Compute the conditional log likelihood of a sequence of tags 
        given emission scores.
        
        Parameters
        ----------
        emissions : torch.Tensor
            Emission score tensor of form (seq_length, batch_size, num_tags)
            if batch_first is False, (batch_size, seq_length, num_tags)
                   
        tags : torch.LongTensor
            Sequence of tags tensor of size (seq_length, batch_size)
            if batch_first is False, (batch_size, seq_length)
                
        mask : Optional[torch.ByteTensor], optional
            Mask tensor of size (seq_length, batch_size)
            if batch_first is False, (batch_size, seq_length)
            The default is None.
            
        reduction : str, optional
            Specifies  the reduction to apply to the output:
            none|sum|mean|token_mean. 
            none: no reduction will be applied.
            sum: the output will be summed over batches. 
            mean: the output will be averaged over batches.
            token_mean: the output will be averaged over tokens.
            
            The default is 'sum'.

        Raises
        ------
        ValueError
            invalid reduction type

        Returns
        -------
        TYPE: torch.Tensor
        The log likelihood. This will have size (batch_size,) 
        if reduction is none, () otherwise.
            
        '''
        
        
        self._validate(emissions, tags=tags, mask=mask)
        if reduction not in ('none', 'sum', 'mean', 'token_mean'):
            raise ValueError(f'invalid reduction: {reduction}')
        if mask is None:
            mask = torch.ones_like(tags, dtype=torch.uint8)

        if self.batch_first:
            emissions = emissions.transpose(0, 1)
            tags = tags.transpose(0, 1)
            mask = mask.transpose(0, 1)

        # shape: (batch_size,)
        numerator = self._compute_score(emissions, tags, mask)
        # shape: (batch_size,)
        denominator = self._compute_normalizer(emissions, mask)
        # shape: (batch_size,)
        llh = numerator - denominator

        if reduction == 'none':
            return llh
        if reduction == 'sum':
            return llh.sum()
        if reduction == 'mean':
            return llh.mean()
        assert reduction == 'token_mean'
        return llh.sum() / mask.float().sum()
        
        
    def decode(self, emissions: torch.Tensor,
               mask: Optional[torch.ByteTensor] = None):
        '''
        Find the most likely tag sequence using Viterbi algorithm.
        
        Parameters
        ----------
        emissions : torch.Tensor
            Emission score tensor of form (seq_length, batch_size, num_tags)
            if batch_first is False, (batch_size, seq_length, num_tags)
            
            
        mask : Optional[torch.ByteTensor], optional
            Mask tensor of size (seq_length, batch_size)
            if batch_first is False, (batch_size, seq_length)
            The default is None.

        Returns
        -------
        List  List[List[int]]
            List of list containing the best tag sequence for each batch
        '''
        
        self._validate(emissions, mask=mask)
        if mask is None:
            mask = emissions.new_ones(emissions.shape[:2], dtype=torch.uint8)

        if self.batch_first:
            emissions = emissions.transpose(0, 1)
            mask = mask.transpose(0, 1)

        return self._viterbi_decode(emissions, mask)
    
    
    def _validate(self, emissions: torch.Tensor, 
                  tags: Optional[torch.LongTensor] = None,
                  mask: Optional[torch.ByteTensor] = None):
        '''
        Justify whether the emissions,tags and mask are in right form
        
        '''
        if emissions.dim() != 3:
            raise ValueError(f'emissions must have dimension of 3, got {emissions.dim()}')
        
        if emissions.size(2) != self.num_tags:
            raise ValueError(
                f'expected last dimension of emissions is {self.num_tags}, '
                f'got {emissions.size(2)}')

        if tags is not None:
            if emissions.shape[:2] != tags.shape:
                raise ValueError(
                    'the first two dimensions of emissions and tags must match, '
                    f'got {tuple(emissions.shape[:2])} and {tuple(tags.shape)}')

        if mask is not None:
            if emissions.shape[:2] != mask.shape:
                raise ValueError(
                    'the first two dimensions of emissions and mask must match, '
                    f'got {tuple(emissions.shape[:2])} and {tuple(mask.shape)}')
                
            # mask for <start>
            no_empty_seq = not self.batch_first and mask[0].all()
            no_empty_seq_bf = self.batch_first and mask[:, 0].all()
            if not no_empty_seq and not no_empty_seq_bf:
                raise ValueError('mask of the first timestep must all be on')
    
        
        
    def _compute_score(self, emissions: torch.Tensor, tags: torch.LongTensor,
                       mask: torch.ByteTensor):
        '''
        Compute the log-likelihood of one specific tag sequence
        will be used in viterbi algorithm to find the best tag sequence 
        
        Parameters
        ----------
        emissions : torch.Tensor (seq_length, batch_size, num_tags)
        tags : torch.LongTensor (seq_length, batch_size)
        mask : torch.ByteTensor (seq_length, batch_size)
            
        Returns
        -------
        score : float
            the log-likelihood of one specific tag sequence
        '''   
        assert emissions.dim() == 3 and tags.dim() == 2
        assert emissions.shape[:2] == tags.shape
        assert emissions.size(2) == self.num_tags
        assert mask.shape == tags.shape
        assert mask[0].all()

        seq_length, batch_size = tags.shape
        mask = mask.float()

        # Start transition score and first emission
        # shape: (batch_size,)
        score = self.start_transitions[tags[0]]
        score += emissions[0, torch.arange(batch_size), tags[0]]

        for i in range(1, seq_length):
            # Transition score to next tag, only added 
            # if next timestep is not pad (mask == 1)
            # shape: (batch_size,)
            score += self.transitions[tags[i - 1], tags[i]] * mask[i]

            # Emission score for next tag, only added 
            # if next timestep is not pad (mask == 1)
            # shape: (batch_size,)
            score += emissions[i, torch.arange(batch_size), tags[i]] * mask[i]

        # End transition score
        # shape: (batch_size,)
        seq_ends = mask.long().sum(dim=0) - 1
        # shape: (batch_size,)
        last_tags = tags[seq_ends, torch.arange(batch_size)]
        # shape: (batch_size,)
        score += self.end_transitions[last_tags]

        return score  
        
        
    
    def _compute_normalizer(self, emissions: torch.Tensor, 
                            mask: torch.ByteTensor):
        # emissions: (seq_length, batch_size, num_tags)
        # mask: (seq_length, batch_size)
        assert emissions.dim() == 3 and mask.dim() == 2
        assert emissions.shape[:2] == mask.shape
        assert emissions.size(2) == self.num_tags
        assert mask[0].all()

        seq_length = emissions.size(0)

        # Start transition score and first emission; score has size of
        # (batch_size, num_tags) where for each batch, the j-th column stores
        # the score that the first timestep has tag j
        # shape: (batch_size, num_tags)
        score = self.start_transitions + emissions[0]

        for i in range(1, seq_length):
            # Broadcast score for every possible next tag
            # #add one dimension -> 
            # shape: (batch_size, num_tags, 1)
            broadcast_score = score.unsqueeze(2) 

            # Broadcast emission score for every possible current tag
            # shape: (batch_size, 1, num_tags)
            broadcast_emissions = emissions[i].unsqueeze(1)

            # Compute the score tensor of size (batch_size, num_tags, num_tags) where
            # for each sample, entry at row i and column j stores the sum of scores of all
            # possible tag sequences so far that end with transitioning from tag i to tag j
            # and emitting
            # shape: (batch_size, num_tags, num_tags)
            next_score = broadcast_score + self.transitions + broadcast_emissions

            # Sum over all possible current tags, but we're in score space, so a sum
            # becomes a log-sum-exp: for each sample, entry i stores the sum of scores of
            # all possible tag sequences so far, that end in tag i
            # shape: (batch_size, num_tags)
            next_score = torch.logsumexp(next_score, dim=1)

            # Set score to the next score if this timestep is valid (mask == 1)
            # shape: (batch_size, num_tags)
            score = torch.where(mask[i].unsqueeze(1), next_score, score)

        # End transition score
        # shape: (batch_size, num_tags)
        score += self.end_transitions

        # Sum (log-sum-exp) over all possible tags
        # shape: (batch_size,)
        return torch.logsumexp(score, dim=1)   
    
    
    def _viterbi_decode(self, emissions: torch.FloatTensor,
                        mask: torch.ByteTensor) -> List[List[int]]:
        # emissions: (seq_length, batch_size, num_tags)
        # mask: (seq_length, batch_size)
        assert emissions.dim() == 3 and mask.dim() == 2
        assert emissions.shape[:2] == mask.shape
        assert emissions.size(2) == self.num_tags
        assert mask[0].all()

        seq_length, batch_size = mask.shape

        # Start transition and first emission
        # shape: (batch_size, num_tags)
        score = self.start_transitions + emissions[0]
        history = []

        # score is a tensor of size (batch_size, num_tags) where for every batch,
        # value at column j stores the score of the best tag sequence so far that ends
        # with tag j
        # history saves where the best tags candidate transitioned from; this is used
        # when we trace back the best tag sequence

        # Viterbi algorithm recursive case: we compute the score of the best tag sequence
        # for every possible next tag
        for i in range(1, seq_length):
            # Broadcast viterbi score for every possible next tag
            # shape: (batch_size, num_tags, 1)
            broadcast_score = score.unsqueeze(2)

            # Broadcast emission score for every possible current tag
            # shape: (batch_size, 1, num_tags)
            broadcast_emission = emissions[i].unsqueeze(1)

            # Compute the score tensor of size (batch_size, num_tags, num_tags) where
            # for each sample, entry at row i and column j stores the score of the best
            # tag sequence so far that ends with transitioning from tag i to tag j and emitting
            # shape: (batch_size, num_tags, num_tags)
            next_score = broadcast_score + self.transitions + broadcast_emission

            # Find the maximum score over all possible current tag
            # shape: (batch_size, num_tags)
            next_score, indices = next_score.max(dim=1)

            # Set score to the next score if this timestep is valid (mask == 1)
            # and save the index that produces the next score
            # shape: (batch_size, num_tags)
            score = torch.where(mask[i].unsqueeze(1), next_score, score)
            history.append(indices)

        # End transition score
        # shape: (batch_size, num_tags)
        score += self.end_transitions

        # Now, compute the best path for each sample

        # shape: (batch_size,)
        seq_ends = mask.long().sum(dim=0) - 1
        best_tags_list = []

        for idx in range(batch_size):
            # Find the tag which maximizes the score at the last timestep; this is our best tag
            # for the last timestep
            _, best_last_tag = score[idx].max(dim=0)
            best_tags = [best_last_tag.item()]

            # We trace back where the best last tag comes from, append that to our best tag
            # sequence, and trace it back again, and so on
            for hist in reversed(history[:seq_ends[idx]]):
                best_last_tag = hist[idx][best_tags[-1]]
                best_tags.append(best_last_tag.item())

            # Reverse the order because we start from the last timestep
            best_tags.reverse()
            best_tags_list.append(best_tags)

        return best_tags_list
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        