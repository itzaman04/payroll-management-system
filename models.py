"""
OOP layer for payroll calculation.
This is intentionally separate from the database layer so it's easy to
point to in an interview: "here is where I used inheritance and
polymorphism to calculate salary differently for each employee type."
"""


class Employee:
    """Base class for a regular employee."""

    def __init__(self, name, base_salary, attendance_percent):
        self.name = name
        self.base_salary = base_salary
        self.attendance_percent = attendance_percent

    def calculate_deduction(self):
        """Deduct salary proportionally for days absent."""
        absent_percent = 100 - self.attendance_percent
        return round((absent_percent / 100) * self.base_salary, 2)

    def calculate_bonus(self):
        """Regular employees get a small attendance bonus if >= 95% present."""
        if self.attendance_percent >= 95:
            return round(self.base_salary * 0.05, 2)
        return 0

    def calculate_salary(self):
        """Final salary = base - deduction + bonus."""
        deduction = self.calculate_deduction()
        bonus = self.calculate_bonus()
        net = self.base_salary - deduction + bonus
        return {
            "base_salary": self.base_salary,
            "deduction": deduction,
            "bonus": bonus,
            "net_salary": round(net, 2),
        }


class Manager(Employee):
    """
    Manager extends Employee (inheritance) but overrides bonus logic
    (polymorphism) — managers get a flat leadership allowance on top of
    the attendance bonus, and a lower attendance threshold since they
    often travel for reviews/meetings.
    """

    def __init__(self, name, base_salary, attendance_percent, team_size):
        super().__init__(name, base_salary, attendance_percent)
        self.team_size = team_size

    def calculate_bonus(self):
        # Override: managers qualify for attendance bonus at a lower bar
        base_bonus = 0
        if self.attendance_percent >= 85:
            base_bonus = self.base_salary * 0.05

        # Leadership allowance scales with team size
        leadership_allowance = min(self.team_size * 500, 5000)
        return round(base_bonus + leadership_allowance, 2)


def build_employee_object(row):
    """
    Factory function: takes a DB row (dict-like) and returns the right
    OOP object (Employee or Manager) — this is the polymorphism in action.
    """
    if row["role"] == "manager":
        return Manager(
            name=row["name"],
            base_salary=row["base_salary"],
            attendance_percent=row["attendance_percent"],
            team_size=row["team_size"] or 0,
        )
    return Employee(
        name=row["name"],
        base_salary=row["base_salary"],
        attendance_percent=row["attendance_percent"],
    )
