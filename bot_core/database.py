import sqlite3

class DatabaseManager:
    def __init__(self, db_path='alerts.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_table()

    def _connect(self):
        """Establishes a persistent connection to the database."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()

    def _create_table(self):
        """Creates the alerts table if it doesn't exist."""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                alert_type TEXT,
                ticker TEXT,
                period INTEGER,
                target_price REAL,
                direction TEXT,
                date1 TEXT,
                price1 REAL,
                date2 TEXT,
                price2 REAL,
                threshold REAL
            )
        ''')
        self.conn.commit()

    def save_alert(self, user_id, alert):
        """Saves a new alert to the database."""
        self.cursor.execute('''
            INSERT INTO alerts (
                user_id, alert_type, ticker, period, target_price, direction,
                date1, price1, date2, price2, threshold
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            alert.get('type'),
            alert.get('ticker'),
            alert.get('period'),
            alert.get('target_price'),
            alert.get('direction'),
            str(alert.get('date1')) if alert.get('date1') else None,
            alert.get('price1'),
            str(alert.get('date2')) if alert.get('date2') else None,
            alert.get('price2'),
            alert.get('threshold')
        ))
        self.conn.commit()
        alert_id = self.cursor.lastrowid
        return alert_id

    def load_alerts(self):
        """Loads all alerts from the database, grouped by user_id."""
        self.cursor.execute("""
            SELECT id, user_id, alert_type, ticker, period, target_price, direction,
                   date1, price1, date2, price2, threshold
            FROM alerts
        """)
        rows = self.cursor.fetchall()
        alerts = {}
        for row in rows:
            user_id = row[1]
            alert = {
                'id': row[0],
                'type': row[2],
                'ticker': row[3],
                'period': row[4],
                'target_price': row[5],
                'direction': row[6],
                'date1': row[7],
                'price1': row[8],
                'date2': row[9],
                'price2': row[10],
                'threshold': row[11]
            }
            alerts.setdefault(user_id, []).append(alert)
        return alerts

    def get_alerts_for_user(self, user_id):
        """Retrieves all alerts for a specific user."""
        self.cursor.execute("SELECT id, alert_type, ticker, period, target_price, direction, date1, price1, date2, price2, threshold FROM alerts WHERE user_id = ?", (user_id,))
        return self.cursor.fetchall()

    def remove_alert(self, alert_id):
        """Removes an alert from the database by its ID."""
        self.cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        self.conn.commit()

    def close_connection(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None

# Example usage (for testing or initial setup)
# if __name__ == '__main__':
#     db_manager = DatabaseManager()
#     # Example of saving an alert
#     # db_manager.save_alert(123, {'type': 'price', 'ticker': 'AAPL', 'target_price': 150.0, 'direction': 'above'})
#     # Example of loading alerts
#     # all_alerts = db_manager.load_alerts()
#     # print(all_alerts)