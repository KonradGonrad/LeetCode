class Solution:
    def numRescueBoats(self, people: list[int], limit: int) -> int:
        boats: int = 0
        people.sort()

        l: int = 0
        r: int = len(people) - 1

        while l <= r:
            if people[l] + people[r] <= limit:
                l +=1
            r -=1
            boats += 1
            
        return boats
        