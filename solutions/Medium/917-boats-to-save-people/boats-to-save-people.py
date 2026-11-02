class Solution:
    def numRescueBoats(self, people: list[int], limit: int) -> int:
        boats = []
        people.sort()

        l: int = 0
        r: int = len(people) - 1

        while l <= r:
            lp: int = people[l]
            rp: int = people[r]

            if lp + rp <= limit:
                boats.append(
                    (lp, rp,)
                )
                l += 1
                r -= 1
            
            else:
                boats.append(
                    (rp,)
                )
                r -=1
            
        return len(boats)
        