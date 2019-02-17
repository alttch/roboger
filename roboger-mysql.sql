-- MySQL dump 10.13  Distrib 5.7.17, for Linux (x86_64)
--
-- Host: localhost    Database: roboger
-- ------------------------------------------------------
-- Server version	5.7.17-0ubuntu0.16.04.1-log

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `addr`
--

DROP TABLE IF EXISTS `addr`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `addr` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `a` char(64) DEFAULT NULL,
  `active` int(11) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `nk` (`a`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `addr`
--

LOCK TABLES `addr` WRITE;
/*!40000 ALTER TABLE `addr` DISABLE KEYS */;
/*!40000 ALTER TABLE `addr` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `endpoint`
--

DROP TABLE IF EXISTS `endpoint`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `endpoint` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `addr_id` int(11) NOT NULL,
  `endpoint_type_id` int(11) NOT NULL DEFAULT '1',
  `data` varchar(256) NOT NULL,
  `data2` varchar(256) DEFAULT NULL,
  `data3` varchar(1024) DEFAULT NULL,
  `active` int(11) NOT NULL DEFAULT '1',
  `skip_dups` int(11) NOT NULL DEFAULT '0',
  `description` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `addr_id` (`addr_id`),
  KEY `endpoint_type_id` (`endpoint_type_id`),
  CONSTRAINT `endpoint_ibfk_1` FOREIGN KEY (`addr_id`) REFERENCES `addr` (`id`),
  CONSTRAINT `endpoint_ibfk_2` FOREIGN KEY (`endpoint_type_id`) REFERENCES `endpoint_type` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `endpoint`
--

LOCK TABLES `endpoint` WRITE;
/*!40000 ALTER TABLE `endpoint` DISABLE KEYS */;
/*!40000 ALTER TABLE `endpoint` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `endpoint_type`
--

DROP TABLE IF EXISTS `endpoint_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `endpoint_type` (
  `id` int(11) NOT NULL,
  `name` char(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `endpoint_type`
--

LOCK TABLES `endpoint_type` WRITE;
/*!40000 ALTER TABLE `endpoint_type` DISABLE KEYS */;
INSERT INTO `endpoint_type` VALUES (2,'email'),(4,'http/json'),(3,'http/post'),(100,'slack'),(101,'telegram');
/*!40000 ALTER TABLE `endpoint_type` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `event`
--

DROP TABLE IF EXISTS `event`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `event` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `addr_id` int(11) NOT NULL,
  `d` datetime DEFAULT NULL,
  `dd` datetime DEFAULT NULL,
  `scheduled` int(11) DEFAULT NULL,
  `delivered` int(11) DEFAULT NULL,
  `location` varchar(255) DEFAULT NULL,
  `keywords` varchar(255) DEFAULT NULL,
  `sender` varchar(255) DEFAULT NULL,
  `level_id` int(11) NOT NULL DEFAULT '20',
  `expires` int(11) DEFAULT NULL,
  `subject` varchar(255) NOT NULL DEFAULT '',
  `msg` varchar(2048) NOT NULL DEFAULT '',
  `media` mediumblob,
  PRIMARY KEY (`id`),
  KEY `addr_id` (`addr_id`),
  KEY `level_id` (`level_id`),
  CONSTRAINT `event_ibfk_1` FOREIGN KEY (`addr_id`) REFERENCES `addr` (`id`) ON DELETE CASCADE,
  CONSTRAINT `event_ibfk_2` FOREIGN KEY (`level_id`) REFERENCES `level` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `event`
--

LOCK TABLES `event` WRITE;
/*!40000 ALTER TABLE `event` DISABLE KEYS */;
/*!40000 ALTER TABLE `event` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `event_queue`
--

DROP TABLE IF EXISTS `event_queue`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `event_queue` (
  `event_id` int(11) NOT NULL,
  `subscription_id` int(11) NOT NULL,
  `status` int(11) NOT NULL DEFAULT '0',
  `dd` datetime DEFAULT NULL,
  PRIMARY KEY (`event_id`,`subscription_id`),
  KEY `event_id` (`event_id`),
  KEY `subscription_id` (`subscription_id`),
  CONSTRAINT `event_queue_ibfk_1` FOREIGN KEY (`event_id`) REFERENCES `event` (`id`) ON DELETE CASCADE,
  CONSTRAINT `event_queue_ibfk_2` FOREIGN KEY (`subscription_id`) REFERENCES `subscription` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `event_queue`
--

LOCK TABLES `event_queue` WRITE;
/*!40000 ALTER TABLE `event_queue` DISABLE KEYS */;
/*!40000 ALTER TABLE `event_queue` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `level`
--

DROP TABLE IF EXISTS `level`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `level` (
  `id` int(11) NOT NULL,
  `name` char(10) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `level`
--

LOCK TABLES `level` WRITE;
/*!40000 ALTER TABLE `level` DISABLE KEYS */;
INSERT INTO `level` VALUES (10,'DEBUG'),(20,'INFO'),(30,'WARNING'),(40,'ERROR'),(50,'CRITICAL');
/*!40000 ALTER TABLE `level` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `subscription`
--

DROP TABLE IF EXISTS `subscription`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `subscription` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `addr_id` int(11) NOT NULL,
  `endpoint_id` int(11) NOT NULL,
  `active` int(11) NOT NULL DEFAULT '1',
  `location` varchar(255) NOT NULL DEFAULT '#',
  `keywords` varchar(255) NOT NULL DEFAULT '',
  `senders` varchar(255) NOT NULL DEFAULT '*',
  `level_id` int(11) NOT NULL DEFAULT '20',
  `level_match` enum('l','g','le','ge','e') NOT NULL DEFAULT 'ge',
  PRIMARY KEY (`id`),
  KEY `addr_id` (`addr_id`),
  KEY `endpoint_id` (`endpoint_id`),
  KEY `level_id` (`level_id`),
  CONSTRAINT `subscription_ibfk_1` FOREIGN KEY (`addr_id`) REFERENCES `addr` (`id`),
  CONSTRAINT `subscription_ibfk_2` FOREIGN KEY (`endpoint_id`) REFERENCES `endpoint` (`id`),
  CONSTRAINT `subscription_ibfk_3` FOREIGN KEY (`level_id`) REFERENCES `level` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `subscription`
--

LOCK TABLES `subscription` WRITE;
/*!40000 ALTER TABLE `subscription` DISABLE KEYS */;
/*!40000 ALTER TABLE `subscription` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2018-05-08 14:49:17
