-- SPDX-License-Identifier: MPL-2.0
-- Disposable test data only. Use the official schema's audit procedure.
BEGIN;
SELECT createAuditRevisionDHCP4(CURRENT_TIMESTAMP, 'all', 'read-only test fixture', false);
INSERT INTO dhcp4_server(tag, description, modification_ts)
VALUES ('test-server', 'Disposable integration server', CURRENT_TIMESTAMP),
       ('other-server', 'Excluded integration server', CURRENT_TIMESTAMP);
INSERT INTO dhcp4_subnet(subnet_id, subnet_prefix, valid_lifetime, renew_timer, rebind_timer)
VALUES (42, '192.0.2.0/24', 600, 200, 400),
       (43, '198.51.100.0/24', 600, 200, 400),
       (44, '203.0.113.0/24', 600, 200, 400),
       (45, '192.0.3.0/24', 1200, 300, 900),
       (46, '192.0.4.0/24', 600, 200, 400);
-- 46 deliberately has no server association.
INSERT INTO dhcp4_subnet_server(subnet_id, server_id, modification_ts)
SELECT fixture.subnet_id, server.id, CURRENT_TIMESTAMP
FROM (VALUES (42, 'all'), (43, 'test-server'), (44, 'other-server'), (45, 'all'))
     AS fixture(subnet_id, tag)
JOIN dhcp4_server AS server ON server.tag = fixture.tag;
UPDATE dhcp4_subnet SET client_classes = '["known"]',
    evaluate_additional_classes = '["audit"]',
    user_context = '{"fixture": "complex", "enabled": true}'
WHERE subnet_id = 42;
INSERT INTO dhcp4_pool(start_address, end_address, subnet_id, client_classes)
VALUES ('192.0.2.10', '192.0.2.20', 42, '["pool-class"]'),
       ('192.0.2.100', '192.0.2.150', 42, '[]'),
       ('192.0.3.10', '192.0.3.30', 45, '[]');
INSERT INTO dhcp4_options(code, formatted_value, space, persistent,
                          dhcp4_subnet_id, scope_id, client_classes)
VALUES (3, '192.0.2.1', 'dhcp4', false, 42, 1, '[]'),
       (6, '192.0.2.53, 192.0.2.54', 'dhcp4', true, 42, 1, '[]');
INSERT INTO dhcp4_options(code, formatted_value, space, persistent,
                          scope_id, pool_id, client_classes)
SELECT 15, 'pool.example', 'dhcp4', false, 5, id, '[]'
FROM dhcp4_pool WHERE start_address = '192.0.2.10';
COMMIT;
