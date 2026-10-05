from collections import Counter

class Solution:
    def topKFrequent(self, nums: List[int], k: int) -> List[int]:
        # returns the list of digits sorted by the apperances score, based on the Counter method with most_common function.
        return [digit for digit, apperances in Counter(nums).most_common(k)]