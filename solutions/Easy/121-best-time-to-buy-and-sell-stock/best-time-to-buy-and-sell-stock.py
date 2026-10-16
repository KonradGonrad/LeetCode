from typing import List

class Solution:
    def maxProfit(self, prices: List[int]) -> int:
        n = len(prices)
        
        if n in (0, 1):
            return 0
        
        maxProfit:  int = 0 # variable that stores the maximum profit
        minPrice:   int = 0 # variable that stores the minimum price
        
        # print(prices[sell], prices[buy])
        for price in prices:
            if price < prices[minPrice]:
                minPrice = prices.index(price)
            else:
                maxProfit = max(maxProfit, price - prices[minPrice])
            
            
        
        return maxProfit
