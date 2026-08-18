from app import Trip, TrackingSession, TrackingPoint
from app.geo import haversine
from decimal import Decimal
from datetime import datetime

def test_haversine():
    d = haversine(0, 0, 0, 1)
    assert 111000 < d < 112000

def test_track_page(client):
    r = client.get('/track')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']

def test_start_stop_flow(client):
    start = client.post('/api/track/start', json={'note':'Test'})
    assert start.status_code == 401
    client.post('/register', data={
        'username': 'trackuser',
        'email': 'trackuser@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'trackuser', 'password': 'secret'})
    start = client.post('/api/track/start', json={'note':'Test'})
    assert start.status_code == 201
    data = start.get_json()
    assert data['session_id'] > 0

    point = client.post('/api/track/point', json={'session_id': data['session_id'], 'lat': 40.0, 'lon': -74.0, 'accuracy': 15})
    assert point.status_code == 200

    stop = client.post('/api/track/stop', json={'session_id': data['session_id']})
    assert stop.status_code == 200
    assert float(stop.get_json()['miles']) >= 0

def test_active_trip_created(client):
    client.post('/register', data={
        'username': 'activeuser',
        'email': 'activeuser@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'activeuser', 'password': 'secret'})
    client.post('/api/track/start', json={'vehicle':'Car2'})
    client.post('/api/track/point', json={'session_id': 1, 'lat': 0, 'lon': 0})
    client.post('/api/track/stop', json={'session_id': 1})
    r = client.get('/trips')
    assert b'Car2' in r.data

def test_track_status(client):
    client.post('/register', data={
        'username': 'statususer',
        'email': 'statususer@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'statususer', 'password': 'secret'})
    client.post('/api/track/start', json={'vehicle':'StatusCar'})
    r = client.get('/api/track/status')
    assert r.status_code == 200
    data = r.get_json()
    assert data['active'] is True
    assert data['vehicle'] == 'StatusCar'
    client.post('/api/track/stop', json={'session_id': data['session_id']})
    r = client.get('/api/track/status')
    assert r.get_json()['active'] is False

def test_cannot_start_twice(client):
    client.post('/register', data={
        'username': 'twiceuser',
        'email': 'twiceuser@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'twiceuser', 'password': 'secret'})
    client.post('/api/track/start', json={'vehicle':'A'})
    first = client.get('/api/track/status').get_json()['session_id']
    r = client.post('/api/track/start', json={'vehicle':'B'})
    assert r.status_code == 409
    client.post('/api/track/stop', json={'session_id': first})

def test_delete_trip(client):
    client.post('/register', data={
        'username': 'deluser',
        'email': 'deluser@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'deluser', 'password': 'secret'})
    client.post('/api/track/start', json={'vehicle':'DelTest'})
    client.post('/api/track/point', json={'session_id': 1, 'lat': 0, 'lon': 0})
    client.post('/api/track/stop', json={'session_id': 1})
    r = client.post('/trips/1/delete', follow_redirects=True)
    assert r.status_code == 200
    assert b'DelTest' not in r.data

def test_start_with_business_type(client):
    client.post('/register', data={
        'username': 'bizuser',
        'email': 'bizuser@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'bizuser', 'password': 'secret'})
    start = client.post('/api/track/start', json={'vehicle':'BizCar', 'trip_type':'business'})
    assert start.status_code == 201
    data = start.get_json()
    assert data['session_id'] > 0
    client.post('/api/track/point', json={'session_id': data['session_id'], 'lat': 0, 'lon': 0})
    stop = client.post('/api/track/stop', json={'session_id': data['session_id']})
    assert stop.status_code == 200
    r = client.get('/trips')
    assert b'BizCar' in r.data

def test_trip_detail_map_renders_for_tracked_trip(client):
    client.post('/register', data={
        'username': 'mapuser',
        'email': 'mapuser@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'mapuser', 'password': 'secret'})
    start = client.post('/api/track/start', json={'vehicle':'MapCar', 'trip_type':'personal'})
    assert start.status_code == 201
    sid = start.get_json()['session_id']
    client.post('/api/track/point', json={'session_id': sid, 'lat': 40.0, 'lon': -74.0, 'accuracy': 15})
    stop = client.post('/api/track/stop', json={'session_id': sid})
    assert stop.status_code == 200
    trip_id = stop.get_json()['trip_id']
    r = client.get(f'/trip/{trip_id}')
    assert r.status_code == 200
    assert b'trip-map' in r.data
    assert b'/api/track/session/' in r.data

def test_settings_page_defaults_to_miles(client):
    r = client.get('/settings')
    assert r.status_code == 200
    assert b'Miles' in r.data
    assert b'Kilometers' in r.data

def test_settings_can_switch_to_kilometers(client):
    r = client.post('/settings', data={'unit': 'km'}, follow_redirects=True)
    assert r.status_code == 200
    assert b'Kilometers' in r.data

def test_reports_page_loads(client):
    r = client.get('/reports')
    assert r.status_code == 200
    assert b'Filters' in r.data

def test_reports_filter_by_month(client):
    client.post('/register', data={
        'username': 'reportuser',
        'email': 'reportuser@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'reportuser', 'password': 'secret'})
    client.post('/api/track/start', json={'vehicle':'ReportCar', 'trip_type':'personal'})
    client.post('/api/track/point', json={'session_id': 1, 'lat': 0, 'lon': 0})
    client.post('/api/track/stop', json={'session_id': 1})
    r = client.get('/reports?month=2026-08')
    assert r.status_code == 200
    assert b'ReportCar' in r.data

def test_reports_filter_by_type(client):
    client.post('/register', data={
        'username': 'bizreport',
        'email': 'bizreport@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'bizreport', 'password': 'secret'})
    client.post('/api/track/start', json={'vehicle':'Biz', 'trip_type':'business'})
    client.post('/api/track/point', json={'session_id': 1, 'lat': 0, 'lon': 0})
    client.post('/api/track/stop', json={'session_id': 1})
    r = client.get('/reports?trip_type=business')
    assert r.status_code == 200
    assert b'Biz' in r.data

def test_register_and_login(client):
    r = client.post('/register', data={
        'username': 'tester',
        'email': 'tester@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Welcome back' in r.data or b'Login' in r.data

    r = client.post('/login', data={'username': 'tester', 'password': 'secret'}, follow_redirects=True)
    assert r.status_code == 200
    assert b'Welcome back' in r.data

def test_logout(client):
    client.post('/register', data={
        'username': 'logoutme',
        'email': 'logoutme@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'logoutme', 'password': 'secret'})
    r = client.get('/logout', follow_redirects=True)
    assert r.status_code == 200
    assert b'Login' in r.data

def test_admin_dashboard_requires_admin(client):
    client.post('/register', data={
        'username': 'norm',
        'email': 'norm@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'norm', 'password': 'secret'})
    r = client.get('/admin')
    assert r.status_code == 302
    assert '/admin/login' in r.headers['Location']

def test_user_trip_isolation(client):
    client.post('/register', data={
        'username': 'alice',
        'email': 'alice@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'alice', 'password': 'secret'})
    client.post('/trips', data={
        'date': '2026-08-17',
        'trip_type': 'personal',
        'vehicle': 'AliceCar',
        'miles': '5',
    })
    client.get('/logout', follow_redirects=True)
    client.post('/register', data={
        'username': 'bob',
        'email': 'bob@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'bob', 'password': 'secret'})
    r = client.get('/trips')
    assert b'AliceCar' not in r.data
    client.post('/trips', data={
        'date': '2026-08-17',
        'trip_type': 'business',
        'vehicle': 'BobCar',
        'miles': '3',
    })
    r = client.get('/trips')
    assert b'BobCar' in r.data

def test_change_password(client):
    client.post('/register', data={
        'username': 'pwuser',
        'email': 'pwuser@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'pwuser', 'password': 'secret'})
    r = client.post('/settings/password', data={
        'current_password': 'secret',
        'new_password': 'newsecret',
        'confirm_password': 'newsecret',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Password updated' in r.data

    client.get('/logout', follow_redirects=True)
    r = client.post('/login', data={'username': 'pwuser', 'password': 'newsecret'}, follow_redirects=True)
    assert r.status_code == 200

def test_change_password_wrong_current(client):
    client.post('/register', data={
        'username': 'badpw',
        'email': 'badpw@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'badpw', 'password': 'secret'})
    r = client.post('/settings/password', data={
        'current_password': 'wrongpass',
        'new_password': 'newsecret',
        'confirm_password': 'newsecret',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Current password is incorrect' in r.data

def test_profile_update(client):
    client.post('/register', data={
        'username': 'profuser',
        'email': 'profuser@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'profuser', 'password': 'secret'})
    r = client.post('/settings/profile', data={
        'username': 'profuser2',
        'email': 'profuser2@example.com',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Profile updated.' in r.data
    r2 = client.get('/settings')
    assert b'profuser2' in r2.data
    assert b'profuser2@example.com' in r2.data

def test_health_endpoint(client):
    r = client.get('/healthz')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'

def test_admin_can_list_and_delete_user_trip(client):
    client.post('/register', data={
        'username': 'tripowner',
        'email': 'tripowner@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'tripowner', 'password': 'secret'})
    client.post('/trips', data={
        'date': '2026-08-17',
        'trip_type': 'business',
        'vehicle': 'AdminTest',
        'miles': '10',
    })
    client.get('/logout', follow_redirects=True)

    client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'})
    r = client.get('/admin/trips')
    assert r.status_code == 200
    assert b'AdminTest' in r.data

    r = client.post('/admin/trips/1/delete', follow_redirects=True)
    assert r.status_code == 200
    assert b'Trip deleted.' in r.data

def test_admin_can_edit_user_trip(client):
    client.post('/register', data={
        'username': 'editowner',
        'email': 'editowner@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'editowner', 'password': 'secret'})
    client.post('/trips', data={
        'date': '2026-08-17',
        'trip_type': 'personal',
        'vehicle': 'OldCar',
        'miles': '5',
    })
    client.get('/logout', follow_redirects=True)

    client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'})
    r = client.post('/admin/trips/1/edit', data={
        'date': '2026-08-18',
        'trip_type': 'business',
        'vehicle': 'NewCar',
        'miles': '12',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Trip updated.' in r.data

def test_non_admin_cannot_access_admin_trip_management(client):
    client.post('/register', data={
        'username': 'normadmin',
        'email': 'normadmin@example.com',
        'password': 'secret',
        'confirm_password': 'secret',
    })
    client.post('/login', data={'username': 'normadmin', 'password': 'secret'})
    r = client.get('/admin/trips')
    assert r.status_code == 302
    assert '/admin/login' in r.headers['Location']
