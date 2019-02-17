CREATE TABLE level (id integer primary key,name char(10));
CREATE TABLE endpoint_type(id PRIMARY KEY,name char(20) not null unique);
CREATE TABLE addr(id integer PRIMARY KEY AUTOINCREMENT,a char(65) not null unique,active int not null default 1);
CREATE TABLE endpoint (id integer PRIMARY KEY AUTOINCREMENT, addr_id int not null, endpoint_type_id int not null,data varchar(256), data2 varchar(256), data3 varchar(1024), active int not null default 1,skip_dups int not null default 0,description varchar(50),foreign key (addr_id) references addr(id),foreign key (endpoint_type_id) references endpoint(id));
CREATE TABLE event(id integer PRIMARY KEY AUTOINCREMENT,addr_id int not null,d datetime, dd datetime, scheduled int, delivered int, location varchar(255),keywords varchar(255),sender varchar(255),level_id int not null default 20,expires int,subject varchar(255) not null default '',msg varchar(2048) not null default '',media blob,foreign key(addr_id) references addr(id),foreign key(level_id) references level(id));
CREATE TABLE subscription(id integer PRIMARY KEY AUTOINCREMENT,addr_id int not null,endpoint_id int not null,active int not null default 1,location varchar(255) not null default '#',keywords varchar(255) not null default '',senders varchar(255) not null default '*', level_id int not null default 20,level_match char(2) not null default 'ge',foreign key(addr_id) references addr(id), foreign key(endpoint_id) references endpoint(id), foreign key(level_id) references level(id));
CREATE TABLE event_queue(event_id int not null, subscription_id int not null, status int not null default 0, dd datetime not null,primary key(event_id,subscription_id), foreign key(event_id) references event(id),foreign key(subscription_id) references subscription(id));

INSERT INTO endpoint_type VALUES(2,'email');
INSERT INTO endpoint_type VALUES(4,'http/json');
INSERT INTO endpoint_type VALUES(3,'http/post');
INSERT INTO endpoint_type VALUES(100,'slack');
INSERT INTO endpoint_type VALUES(101,'telegram');

INSERT INTO level VALUES(10, 'DEBUG');
INSERT INTO level VALUES(20, 'INFO');
INSERT INTO level VALUES(30, 'WARNING');
INSERT INTO level VALUES(40, 'ERROR');
INSERT INTO level VALUES(50, 'CRITICAL');

