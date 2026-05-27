from src.portfolio.position_manager import PositionManager

pm = PositionManager(50000)

print("\nDefault")
print(pm.calculate_position())

print("\nGood Setup")
print(pm.calculate_position(setup_type="good"))

print("\nHigh Conviction 60%")
print(
    pm.calculate_position(
        override=True,
        override_percent=0.60
    )
)

print("\nTry 80% Override")

try:
    print(
        pm.calculate_position(
            override=True,
            override_percent=0.80
        )
    )
except Exception as e:
    print("Blocked:", e)
