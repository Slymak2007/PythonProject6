import logging

# Без цього попередження логера (які тести навмисно викликають) засмічують вивід у stderr.
logging.getLogger().addHandler(logging.NullHandler())
