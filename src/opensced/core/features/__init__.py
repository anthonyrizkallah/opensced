"""The parts of a clearing. Each module adds its variables and rows to the program; core/model.py puts them together.

  balance    energy offer blocks and the power balance (always on)
  reserves   reserve awards, reserve offers and the reserve demand curves
  storage    battery state of charge under energy and reserve awards
  network    transmission constraints and node prices
"""
