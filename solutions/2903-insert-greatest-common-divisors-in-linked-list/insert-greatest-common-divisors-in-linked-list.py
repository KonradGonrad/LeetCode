# from typing import Optional
import math
# from typing import List

# def createListNode(input = List) -> ListNode:
#   if not input:
#     return None

#   # Returns LinkedList[head[0], None]
#   head = ListNode(input[0])
#   current = head

#   for digit in input[1:]:
#     # from LinkedList[head[0], None] -> LinkedList[head[0], LinkedList[digit, None]]
#     current.next = ListNode(digit)
#     current = current.next

#   # returns LinkedList[head[0], LinkedList[digit, LinkedList[digit+, ...]]]
#   return head

# # Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next

# def printListNode(head):
#   result = []

#   while head:
#     result.append(head.val)
#     head = head.next

#   print(result)

class Solution:
    def insertGreatestCommonDivisors(self, head: Optional[ListNode]) -> Optional[ListNode]:
      current = head
        
      while current and current.next:
        gcd = math.gcd(
            current.val, current.next.val
        )
        
        newNode = ListNode(
            gcd
        )
        newNode.next = current.next

        current.next = newNode
        current = newNode.next
        
      return head
