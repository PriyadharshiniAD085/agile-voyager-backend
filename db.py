import os
import sqlite3

# Get database path relative to this file
DB_PATH = os.path.join(os.path.dirname(__file__), "ai_trip.db")

# Initialize global connection and cursor
conn = None
cursor = None

def get_connection():
    global conn, cursor
    if conn is None:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            print(f"✅ Connected to SQLite database at {DB_PATH}")
            init_tables()  # Create tables if they don't exist
            migrate_database()  # Apply any missing columns or indexes
        except Exception as e:
            print("⚠️ SQLite connection failed:", e)
            conn = None
            cursor = None
    return conn, cursor

def init_tables():
    """Create tables if they don't exist"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE NOT NULL,
            dob TEXT,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS itineraries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            lat REAL,
            lng REAL,
            day INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            user_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS confirmed_trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            destination TEXT,
            plan_text TEXT,
            total_budget REAL,
            days INTEGER,
            trip_type TEXT,
            members INTEGER,
            itinerary_json TEXT,
            completed INTEGER DEFAULT 0,
            year INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trip_id) REFERENCES confirmed_trips(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    print("✅ Database tables initialized")

def migrate_database():
    """Apply database migrations for new columns and indexes"""
    try:
        # Check if 'completed' column exists in confirmed_trips
        cursor.execute("PRAGMA table_info(confirmed_trips)")
        columns = [column[1] for column in cursor.fetchall()]
        
        print(f"🔍 Current confirmed_trips columns: {', '.join(columns)}")
        
        # FIX UNIQUE CONSTRAINT on user_id
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='confirmed_trips'")
        table_def = cursor.fetchone()
        if table_def and table_def[0]:
            table_sql = table_def[0]
            # Check if there's a UNIQUE constraint on user_id
            if 'UNIQUE' in table_sql.upper() and 'user_id' in table_sql:
                print("⚠️ Found UNIQUE constraint on user_id - fixing...")
                
                # Backup existing data
                cursor.execute("SELECT COUNT(*) FROM confirmed_trips")
                count = cursor.fetchone()[0]
                print(f"📊 Backing up {count} existing trips...")
                
                # Rename old table
                cursor.execute("ALTER TABLE confirmed_trips RENAME TO confirmed_trips_old")
                
                # Create new table with correct schema
                cursor.execute("""
                    CREATE TABLE confirmed_trips (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        destination TEXT,
                        plan_text TEXT,
                        total_budget REAL,
                        days INTEGER,
                        trip_type TEXT,
                        members INTEGER,
                        itinerary_json TEXT,
                        completed INTEGER DEFAULT 0,
                        year INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """)
                
                # Copy data back
                if count > 0:
                    cursor.execute("""
                        INSERT INTO confirmed_trips 
                        (id, user_id, destination, plan_text, total_budget, days, 
                         trip_type, members, itinerary_json, completed, year, created_at)
                        SELECT id, user_id, destination, plan_text, total_budget, days, 
                               trip_type, members, itinerary_json, completed, year, created_at
                        FROM confirmed_trips_old
                    """)
                
                # Drop old table
                cursor.execute("DROP TABLE confirmed_trips_old")
                conn.commit()
                print("✅ Fixed UNIQUE constraint - users can now have multiple trips!")
                
                # Refresh columns list
                cursor.execute("PRAGMA table_info(confirmed_trips)")
                columns = [column[1] for column in cursor.fetchall()]
        
        # Add 'plan_text' column if it doesn't exist
        if 'plan_text' not in columns:
            print("🔄 Adding 'plan_text' column to confirmed_trips table...")
            cursor.execute("ALTER TABLE confirmed_trips ADD COLUMN plan_text TEXT")
            conn.commit()
            print("✅ Added 'plan_text' column")
        
        # Add 'completed' column if it doesn't exist
        if 'completed' not in columns:
            print("🔄 Adding 'completed' column to confirmed_trips table...")
            cursor.execute("ALTER TABLE confirmed_trips ADD COLUMN completed INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added 'completed' column")
        
        # Add 'year' column if it doesn't exist
        if 'year' not in columns:
            print("🔄 Adding 'year' column to confirmed_trips table...")
            cursor.execute("ALTER TABLE confirmed_trips ADD COLUMN year INTEGER")
            conn.commit()
            print("✅ Added 'year' column")
            
            # Update existing trips to extract year from created_at
            print("🔄 Updating existing trips with year from created_at...")
            cursor.execute("""
                UPDATE confirmed_trips 
                SET year = CAST(strftime('%Y', created_at) AS INTEGER) 
                WHERE year IS NULL
            """)
            conn.commit()
            print("✅ Updated existing trips with year")
        
        # Add 'destination' column if it doesn't exist
        if 'destination' not in columns:
            print("🔄 Adding 'destination' column to confirmed_trips table...")
            cursor.execute("ALTER TABLE confirmed_trips ADD COLUMN destination TEXT")
            conn.commit()
            print("✅ Added 'destination' column")
        
        # Add 'total_budget' column if it doesn't exist
        if 'total_budget' not in columns:
            print("🔄 Adding 'total_budget' column to confirmed_trips table...")
            cursor.execute("ALTER TABLE confirmed_trips ADD COLUMN total_budget REAL")
            conn.commit()
            print("✅ Added 'total_budget' column")
        
        # Add 'days' column if it doesn't exist
        if 'days' not in columns:
            print("🔄 Adding 'days' column to confirmed_trips table...")
            cursor.execute("ALTER TABLE confirmed_trips ADD COLUMN days INTEGER")
            conn.commit()
            print("✅ Added 'days' column")
        
        # Add 'trip_type' column if it doesn't exist
        if 'trip_type' not in columns:
            print("🔄 Adding 'trip_type' column to confirmed_trips table...")
            cursor.execute("ALTER TABLE confirmed_trips ADD COLUMN trip_type TEXT")
            conn.commit()
            print("✅ Added 'trip_type' column")
        
        # Add 'members' column if it doesn't exist
        if 'members' not in columns:
            print("🔄 Adding 'members' column to confirmed_trips table...")
            cursor.execute("ALTER TABLE confirmed_trips ADD COLUMN members INTEGER")
            conn.commit()
            print("✅ Added 'members' column")
        
        # Add 'itinerary_json' column if it doesn't exist
        if 'itinerary_json' not in columns:
            print("🔄 Adding 'itinerary_json' column to confirmed_trips table...")
            cursor.execute("ALTER TABLE confirmed_trips ADD COLUMN itinerary_json TEXT")
            conn.commit()
            print("✅ Added 'itinerary_json' column")
        
        # Create indexes for better query performance
        print("🔄 Creating database indexes...")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_confirmed_trips_user_id 
            ON confirmed_trips(user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_confirmed_trips_completed 
            ON confirmed_trips(completed)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_confirmed_trips_year 
            ON confirmed_trips(year)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expenses_trip_id 
            ON expenses(trip_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_itineraries_user_id 
            ON itineraries(user_id)
        """)
        
        conn.commit()
        print("✅ Database indexes created")
        
        # Verify the migration
        cursor.execute("PRAGMA table_info(confirmed_trips)")
        columns_after = [column[1] for column in cursor.fetchall()]
        print(f"✅ confirmed_trips columns after migration: {', '.join(columns_after)}")
        
    except Exception as e:
        print(f"⚠️ Database migration warning: {e}")
        # Don't fail if migration has issues, just warn
        if conn:
            conn.rollback()

def get_database_stats():
    """Get database statistics for debugging"""
    try:
        stats = {}
        
        # Count users
        cursor.execute("SELECT COUNT(*) FROM users")
        stats['users'] = cursor.fetchone()[0]
        
        # Count trips
        cursor.execute("SELECT COUNT(*) FROM confirmed_trips")
        stats['trips'] = cursor.fetchone()[0]
        
        # Count completed trips
        cursor.execute("SELECT COUNT(*) FROM confirmed_trips WHERE completed = 1")
        stats['completed_trips'] = cursor.fetchone()[0]
        
        # Count expenses
        cursor.execute("SELECT COUNT(*) FROM expenses")
        stats['expenses'] = cursor.fetchone()[0]
        
        # Count feedbacks
        cursor.execute("SELECT COUNT(*) FROM feedbacks")
        stats['feedbacks'] = cursor.fetchone()[0]
        
        return stats
    except Exception as e:
        print(f"⚠️ Error getting database stats: {e}")
        return {}

# Initialize immediately when imported
get_connection()

# Print database stats on initialization
try:
    stats = get_database_stats()
    if stats:
        print(f"📊 Database Stats: {stats['users']} users, {stats['trips']} trips ({stats['completed_trips']} completed), {stats['expenses']} expenses")
except:
    pass