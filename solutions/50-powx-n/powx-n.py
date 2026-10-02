class Solution:
    def myPow(self, x: float, n: int) -> float:
      
      def calc_pow(base, exp):
        if exp == 0:
          return 1.0

        half = calc_pow(base, exp // 2)

        if exp % 2 == 0:
                return half * half
        else:
            return base * half * half

      res = calc_pow(x, abs(n))

      return res if n >= 0 else 1.0 / res
